package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/boxBuilder1993/work-planner/backend/internal/auth"
	"github.com/boxBuilder1993/work-planner/backend/internal/handler"
	"github.com/boxBuilder1993/work-planner/backend/internal/middleware"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
	"github.com/boxBuilder1993/work-planner/backend/internal/worker"
	"github.com/jackc/pgx/v5/pgxpool"
)

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	// Load config from environment.
	databaseURL := envOrDefault("DATABASE_URL", "postgres://workplanner:workplanner@localhost:5432/workplanner?sslmode=disable")
	jwtSecret := envOrDefault("JWT_SECRET", "")
	googleClientID := envOrDefault("GOOGLE_CLIENT_ID", "")
	port := envOrDefault("PORT", "8080")
	corsOrigins := envOrDefault("CORS_ORIGINS", "http://localhost:5173")
	migrationsDir := envOrDefault("MIGRATIONS_DIR", "./migrations")
	internalAPIKey := envOrDefault("INTERNAL_API_KEY", "")

	if jwtSecret == "" {
		log.Fatal("JWT_SECRET environment variable is required")
	}
	if googleClientID == "" {
		log.Println("WARNING: GOOGLE_CLIENT_ID not set — Google token audience validation is disabled")
	}

	// Connect to Postgres with retry.
	var pool *pgxpool.Pool
	for i := 0; i < 30; i++ {
		var err error
		pool, err = pgxpool.New(ctx, databaseURL)
		if err == nil {
			if err = pool.Ping(ctx); err == nil {
				break
			}
			pool.Close()
		}
		log.Printf("Waiting for database (attempt %d/30): %v", i+1, err)
		select {
		case <-ctx.Done():
			log.Fatal("Interrupted while waiting for database")
		case <-time.After(2 * time.Second):
		}
		pool = nil
	}
	if pool == nil {
		log.Fatal("Failed to connect to database after 30 attempts")
	}
	defer pool.Close()
	log.Println("Connected to database")

	// Run migrations.
	if err := store.RunMigrations(ctx, pool, migrationsDir); err != nil {
		log.Fatalf("Failed to run migrations: %v", err)
	}
	log.Println("Migrations complete")

	// Initialize layers.
	st := store.New(pool)
	a := auth.New(googleClientID, jwtSecret)

	authHandler := handler.NewAuthHandler(a, st)
	taskHandler := handler.NewTaskHandler(st)
	commentHandler := handler.NewCommentHandler(st)
	recurringHandler := handler.NewRecurringHandler(st)
	internalHandler := handler.NewInternalHandler(st)

	// Build router.
	mux := http.NewServeMux()

	// Public routes.
	mux.HandleFunc("/auth/local", authHandler.HandleLocalAuth)
	mux.HandleFunc("/auth/google", authHandler.HandleGoogleAuth)
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if err := pool.Ping(r.Context()); err != nil {
			w.WriteHeader(http.StatusServiceUnavailable)
			w.Write([]byte(`{"status":"unhealthy","error":"database unreachable"}`))
			return
		}
		w.Write([]byte(`{"status":"ok"}`))
	})

	// Protected routes — wrap with auth middleware.
	protectedMux := http.NewServeMux()

	// Task routes — use a single handler func to route by path pattern.
	protectedMux.HandleFunc("/api/tasks/", func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimSuffix(r.URL.Path, "/")

		switch {
		case strings.HasSuffix(path, "/comments"):
			commentHandler.ServeHTTP(w, r)
		case strings.HasSuffix(path, "/recurring"):
			recurringHandler.ServeHTTP(w, r)
		default:
			taskHandler.ServeHTTP(w, r)
		}
	})

	// Exact match for /api/tasks (no trailing segment).
	protectedMux.HandleFunc("/api/tasks", func(w http.ResponseWriter, r *http.Request) {
		taskHandler.ServeHTTP(w, r)
	})

	// Comment delete route.
	protectedMux.HandleFunc("/api/comments/", func(w http.ResponseWriter, r *http.Request) {
		commentHandler.ServeDeleteHTTP(w, r)
	})

	// Internal routes — require internal API key, no user scoping.
	internalMux := http.NewServeMux()
	internalMux.HandleFunc("/api/internal/tasks/", func(w http.ResponseWriter, r *http.Request) {
		internalHandler.ServeHTTP(w, r)
	})
	internalMux.HandleFunc("/api/internal/tasks", func(w http.ResponseWriter, r *http.Request) {
		internalHandler.ServeHTTP(w, r)
	})
	internalMux.HandleFunc("/api/internal/comments/", func(w http.ResponseWriter, r *http.Request) {
		internalHandler.ServeHTTP(w, r)
	})
	internalMux.HandleFunc("/api/internal/comments", func(w http.ResponseWriter, r *http.Request) {
		internalHandler.ServeHTTP(w, r)
	})
	internalMux.HandleFunc("/api/internal/work-items/", func(w http.ResponseWriter, r *http.Request) {
		internalHandler.ServeHTTP(w, r)
	})
	internalMux.HandleFunc("/api/internal/work-items", func(w http.ResponseWriter, r *http.Request) {
		internalHandler.ServeHTTP(w, r)
	})

	// Apply auth middleware to protected routes.
	authMw := middleware.AuthMiddleware(a, internalAPIKey)
	mux.Handle("/api/internal/", authMw(handler.RequireInternal(internalMux)))
	mux.Handle("/api/", authMw(protectedMux))

	// Apply global middleware.
	var rootHandler http.Handler = mux
	rootHandler = middleware.CORS(corsOrigins)(rootHandler)
	rootHandler = middleware.Logging(rootHandler)

	// Start recurring worker with WaitGroup for graceful shutdown.
	var wg sync.WaitGroup
	rw := worker.NewRecurringWorker(st)
	wg.Add(1)
	go func() {
		defer wg.Done()
		rw.Start(ctx)
	}()

	// Start server.
	srv := &http.Server{
		Addr:    ":" + port,
		Handler: rootHandler,
	}

	go func() {
		log.Printf("Server starting on :%s", port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server error: %v", err)
		}
	}()

	<-ctx.Done()
	log.Println("Shutting down...")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("Shutdown error: %v", err)
	}

	wg.Wait()
	log.Println("Server stopped")
}

func envOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
