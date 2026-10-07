FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .

# The header's GitHub link, and the "Report SMILES on GitHub" link on results
# Orthonym could not name. Both read src/lib/github.js.
#
# It has to arrive as a BUILD arg and not as a runtime environment variable,
# because vite substitutes `import.meta.env.VITE_*` into the bundle when the
# bundle is written -- there is no runtime lookup left to influence. A value
# in compose's `environment:` block, or in the root `.env` the backend
# reads, would reach the container and do nothing at all.
#
# `VITE_`-prefixed, which is not decoration: vite exposes ONLY that prefix to
# client code, so nothing else in the build environment can leak into a
# public bundle by accident. Verified by building with a probe value and
# grepping the output, not assumed.
#
# THIS SITE's repository is the default, because it is public:
# github.com/Steinbeck-Lab/Orthonym-Web. It is NOT the naming engine -- the
# Orthonym engine's repository is private and answers 404, which is why this
# arg was empty for a while, and the prose in About.jsx and Terms.jsx saying
# the engine is not public is still true and must not be edited to match this
# link.
#
# Override to point a fork at its own source. The literal value `none` ships
# no link, no notch separator and no report link (src/lib/github.js), which
# is the only way to turn them off -- an empty string here would just fall
# through to that file's own default.
ARG VITE_GITHUB_URL="https://github.com/Steinbeck-Lab/Orthonym-Web"

# Matomo page counting (src/lib/matomo.js), BUILD args for the same reason as
# the one above. EMPTY by default, and empty means OFF -- the opposite of
# VITE_GITHUB_URL's convention, on purpose: this repository is public, and a
# default here would make every fork's visitors report into one deployment's
# analytics. Both must be set for a tracker to ship; Privacy.jsx switches its
# analytics paragraphs on the same condition.
ARG VITE_MATOMO_URL=""
ARG VITE_MATOMO_SITE_ID=""
RUN npm run build

FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
