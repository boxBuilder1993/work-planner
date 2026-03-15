FROM golang:1.25-alpine AS build
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o server ./cmd/server

FROM alpine:3.20
COPY --from=build /app/server /server
COPY --from=build /app/migrations /migrations
EXPOSE 8080
CMD ["/server"]
