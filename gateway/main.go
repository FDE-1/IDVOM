package main

import (
	"context"
	"crypto/subtle"
	"encoding/base64"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// parseUsers parses BASIC_USERS env as "user:pass,user2:pass2"
func parseUsers(s string) map[string]string {
	m := map[string]string{}
	for _, pair := range strings.Split(s, ",") {
		pair = strings.TrimSpace(pair)
		if pair == "" {
			continue
		}
		parts := strings.SplitN(pair, ":", 2)
		if len(parts) != 2 {
			continue
		}
		m[parts[0]] = parts[1]
	}
	return m
}

// basicAuth returns username and ok
func basicAuth(r *http.Request, users map[string]string) (string, bool) {
	a := r.Header.Get("Authorization")
	if a == "" || !strings.HasPrefix(a, "Basic ") {
		return "", false
	}
	raw, err := base64.StdEncoding.DecodeString(strings.TrimPrefix(a, "Basic "))
	if err != nil {
		return "", false
	}
	creds := strings.SplitN(string(raw), ":", 2)
	if len(creds) != 2 {
		return "", false
	}
	user, pass := creds[0], creds[1]
	expected, ok := users[user]
	if !ok {
		return "", false
	}
	if subtle.ConstantTimeCompare([]byte(pass), []byte(expected)) != 1 {
		return "", false
	}
	return user, true
}

// authMiddleware protects /api/* and sets X-User header when auth succeeds
func authMiddleware(users map[string]string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/api/") {
			next.ServeHTTP(w, r)
			return
		}
		if user, ok := basicAuth(r, users); ok {
			r2 := r.Clone(r.Context())
			r2.Header.Set("X-User", user)
			next.ServeHTTP(w, r2)
			return
		}
		w.Header().Set("WWW-Authenticate", "Basic realm=\"student\"")
		w.WriteHeader(http.StatusUnauthorized)
		_, _ = w.Write([]byte("unauthorized"))
	})
}

// proxyHandler builds a reverse proxy from a base URL and a path prefix to strip
func proxyHandler(base *url.URL, stripPrefix string) http.Handler {
	proxy := httputil.NewSingleHostReverseProxy(base)
	origDirector := proxy.Director
	proxy.Director = func(r *http.Request) {
		origDirector(r)
		// rewrite path by stripping the prefix
		if strings.HasPrefix(r.URL.Path, stripPrefix) {
			r.URL.Path = strings.TrimPrefix(r.URL.Path, stripPrefix)
			if !strings.HasPrefix(r.URL.Path, "/") {
				r.URL.Path = "/" + r.URL.Path
			}
		}
	}
	return proxy
}

func main() {
	listen := getenv("LISTEN_ADDR", ":8080")
	catalogBase := mustURL("CATALOG_BASE_URL")
	ordersBase := mustURL("ORDERS_BASE_URL")
	users := parseUsers(os.Getenv("BASIC_USERS"))
	if len(users) == 0 {
		log.Fatal("BASIC_USERS is required, e.g. 'alice:secret,bob:secret'")
	}

	log.Printf("config: listen=%s catalog=%s orders=%s users=%d",
		listen, catalogBase.String(), ordersBase.String(), len(users))

	reg := prometheus.NewRegistry()
	reg.MustRegister(prometheus.NewGoCollector())
	reg.MustRegister(prometheus.NewProcessCollector(prometheus.ProcessCollectorOpts{}))

	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	mux.Handle("/metrics", promhttp.HandlerFor(reg, promhttp.HandlerOpts{}))
	mux.HandleFunc("/whoami", func(w http.ResponseWriter, r *http.Request) {
		user, ok := basicAuth(r, users)
		if !ok {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		_, _ = w.Write([]byte(user))
	})

	// Proxies (protected by /api/* rule)
	mux.Handle("/api/catalog/", proxyHandler(catalogBase, "/api/catalog"))
	mux.Handle("/api/orders/", proxyHandler(ordersBase, "/api/orders"))

	// Wrap with auth + logging
	h := loggingMiddleware(authMiddleware(users, mux))

	srv := &http.Server{Addr: listen, Handler: h, ReadHeaderTimeout: 5 * time.Second}
	go func() {
		log.Printf("gateway listening on %s", listen)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}()

	// Graceful shutdown
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	<-sig
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(ctx)
}

func getenv(k, def string) string {
	v := os.Getenv(k)
	if v == "" {
		return def
	}
	return v
}

// mustURL reads env var `name` and parses it as URL; logs a helpful fatal message on error.
func mustURL(name string) *url.URL {
	s := os.Getenv(name)
	if s == "" {
		log.Fatalf("%s is not set or empty", name)
	}
	u, err := url.Parse(s)
	if err != nil {
		log.Fatalf("%s has an invalid URL %q: %v", name, s, err)
	}
	if u.Scheme == "" || u.Host == "" {
		log.Fatalf("%s must include scheme and host, got %q", name, s)
	}
	return u
}

// Simple request logger
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &respWriter{ResponseWriter: w, status: 200}
		next.ServeHTTP(rw, r)
		log.Printf("%s %s %d %s", r.Method, r.URL.Path, rw.status, time.Since(start))
	})
}

type respWriter struct {
	http.ResponseWriter
	status int
}

func (rw *respWriter) WriteHeader(code int) {
	rw.status = code
	rw.ResponseWriter.WriteHeader(code)
}

