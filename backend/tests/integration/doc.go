// Package integration holds black-box HTTP integration tests that run
// against a live backend (see docker-compose.test.yml). The test files are
// tagged `//go:build integration` so they're excluded from the default
// `go test ./...` (which has no live server). Run them with the stack up:
//
//	make test-e2e            # one-shot: bring up stack, test, tear down
//	make test-integration    # against an already-running test stack
//
// This untagged file exists so the package always has a buildable non-test
// source file — keeps `go vet ./...` / `go build ./...` happy when the
// integration tag is absent.
package integration
