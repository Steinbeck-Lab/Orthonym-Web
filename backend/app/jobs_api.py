"""The batch job endpoints.

Kept in its own router rather than main.py: six endpoints plus CSV
streaming would double that file, and these share nothing with the
single-molecule endpoints except the settings object.
"""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from rdkit import Chem

from app import redis_store
from app.core.config import get_settings
from app.depiction import mol_to_svg_data_uri
from app.inputs import InputFormat, TooManyMolecules, parse, sniff
from app.schemas import (
    BatchRow,
    JobEnvelope,
    JobResultsResponse,
    JobStatusResponse,
    ParsePreviewResponse,
)
from app.tasks import dispatch_batch, translate_job_inline

router = APIRouter()

PREVIEW_SAMPLE = 5

CSV_COLUMNS = [
    "index",
    "input",
    "input_id",
    "smiles",
    "name",
    "status",
    "roundtrip_smiles",
    "roundtrip_match",
    "formula",
    "limit_code",
    "error",
]


class TextPayload(BaseModel):
    text: str
    best_effort: bool = True


async def _read_input(
    request: Request, file: UploadFile | None
) -> tuple[bytes, bool]:
    """Accept either a multipart file or a JSON {"text": ...} body.

    Size is checked before the bytes are handed on, so an oversized upload
    is rejected rather than parsed.

    A multipart request with no `file` part has already had its body stream
    consumed by the time FastAPI resolves `file` to None, so falling
    through to request.json() would raise a bare RuntimeError ("Stream
    consumed") -- and an empty or non-JSON body raises a bare
    JSONDecodeError, and JSON missing "text" raises pydantic's
    ValidationError. All three would otherwise surface as a raw 500. Caught
    here so a malformed request comes back as an honest 400 instead.
    """
    settings = get_settings()
    if file is not None:
        data = await file.read()
        if len(data) > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File is larger than the {settings.MAX_FILE_SIZE_MB} MB limit"
                ),
            )
        return data, True

    try:
        body = await request.json()
        payload = TextPayload.model_validate(body)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Expected a file upload or a JSON body with a 'text' field",
        ) from exc

    data = payload.text.encode("utf-8")
    if len(data) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Input is larger than the {settings.MAX_FILE_SIZE_MB} MB limit",
        )
    return data, payload.best_effort


def _parse_or_400(data: bytes, max_molecules: int):
    fmt = sniff(data)
    try:
        molecules = parse(data, fmt, max_molecules)
    except TooManyMolecules as exc:
        raise HTTPException(
            status_code=413,
            detail=f"Input exceeds the {exc.limit}-molecule limit",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not read this {fmt.value}: {exc}"
        ) from exc
    if not molecules:
        raise HTTPException(
            status_code=400,
            detail=f"No molecules found in this {fmt.value} input",
        )
    return fmt, molecules


def prepared_payload(molecules) -> list[dict]:
    """The wire form a task receives: JSON-serialisable, index preserved."""
    return [
        {
            "index": m.index,
            "raw_input": m.raw_input,
            "input_id": m.input_id,
            "smiles": m.smiles,
            "error": m.error,
        }
        for m in molecules
    ]


@router.post("/api/parse-preview", response_model=ParsePreviewResponse)
async def parse_preview(
    request: Request, file: UploadFile | None = File(default=None)
) -> ParsePreviewResponse:
    settings = get_settings()
    data, _ = await _read_input(request, file)
    fmt, molecules = _parse_or_400(data, settings.MAX_BATCH_SIZE)
    sample = [
        BatchRow(
            index=m.index,
            input=m.raw_input,
            input_id=m.input_id,
            smiles=m.smiles,
            status="error" if m.error else "abstain",
            error=m.error,
        )
        for m in molecules[:PREVIEW_SAMPLE]
    ]
    errors = [m.error for m in molecules if m.error][:PREVIEW_SAMPLE]
    return ParsePreviewResponse(
        format=fmt.value,
        molecule_count=len(molecules),
        sample=sample,
        errors=errors,
    )


@router.post("/api/jobs", response_model=JobEnvelope)
async def create_job(
    request: Request, file: UploadFile | None = File(default=None)
) -> JobEnvelope:
    settings = get_settings()
    data, best_effort = await _read_input(request, file)
    fmt, molecules = _parse_or_400(data, settings.MAX_BATCH_SIZE)

    job_id = uuid.uuid4().hex
    client_ip = request.client.host if request.client else "unknown"
    redis_store.create_job(job_id, len(molecules), fmt.value, client_ip)

    prepared = prepared_payload(molecules)
    if len(prepared) <= settings.FAST_PATH_MAX_MOLECULES:
        translate_job_inline.apply_async(
            args=[job_id, prepared, best_effort], queue="fast"
        )
    else:
        dispatch_batch(job_id, prepared, best_effort, settings.BATCH_CHUNK_SIZE)

    return JobEnvelope(
        job_id=job_id, molecule_count=len(molecules), status="queued"
    )


def _meta_or_error(job_id: str) -> dict[str, str]:
    meta = redis_store.read_job_meta(job_id)
    if meta is not None:
        return meta
    # No meta. If rows survive, the meta key aged out: the job existed and
    # is gone, which is 410, not 404. This is why there is no "expired"
    # status value -- there is nothing left to report a status from.
    if redis_store.get_redis().exists(redis_store.job_rows_key(job_id)):
        raise HTTPException(status_code=410, detail="This job has expired")
    raise HTTPException(status_code=404, detail="No such job")


@router.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str) -> JobStatusResponse:
    meta = _meta_or_error(job_id)
    return JobStatusResponse(
        job_id=job_id,
        status=meta["status"],
        total=int(meta["total"]),
        done=int(meta["done"]),
        failed=int(meta["failed"]),
        created_at=int(meta["created"]),
        expires_at=int(meta["expires"]),
    )


@router.get("/api/jobs/{job_id}/results", response_model=JobResultsResponse)
def job_results(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> JobResultsResponse:
    meta = _meta_or_error(job_id)
    rows = redis_store.read_rows(job_id, offset, limit)
    return JobResultsResponse(
        job_id=job_id,
        offset=offset,
        limit=limit,
        total=int(meta["total"]),
        rows=[BatchRow.model_validate(r) for r in rows],
    )


@router.get("/api/jobs/{job_id}/results.csv")
def job_results_csv(job_id: str) -> StreamingResponse:
    _meta_or_error(job_id)

    def generate():
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        yield buffer.getvalue()
        # Stream page by page: a 10,000-row job is never held in memory.
        for row in redis_store.iter_all_rows(job_id):
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow(row)
            yield buffer.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="stitch-{job_id}.csv"'
        },
    )


@router.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, str]:
    _meta_or_error(job_id)
    client = redis_store.get_redis()
    for key in client.scan_iter(match=f"stitch:job:{job_id}*"):
        client.delete(key)
    return {"job_id": job_id, "status": "deleted"}


@router.get("/api/depict")
def depict(smiles: str = Query(..., min_length=1)) -> dict[str, str | None]:
    """One molecule's 2D structure. Pure RDKit: no JVM, no worker, no queue.

    This is what lets a batch results table draw a row on demand, since
    batch rows deliberately carry no depiction.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {
            "depiction_svg": None,
            "error": "Could not parse this SMILES string",
        }
    return {"depiction_svg": mol_to_svg_data_uri(mol), "error": None}
