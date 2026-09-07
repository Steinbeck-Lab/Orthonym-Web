FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .

# The header's GitHub link, absent by default.
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
# Empty is the honest default: github.com/Kohulan/OpenSTOUT is private and
# answers 404, so shipping no link is correct until some repository is
# published. Navigation.jsx renders the link and its notch separator only
# when this is set; About.jsx and Terms.jsx state the same fact in prose and
# must be edited by hand when it changes.
ARG VITE_GITHUB_URL=""
RUN npm run build

FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
