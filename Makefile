# Stock Lakehouse Platform — Makefile
# Tác giả: dev team. Chuẩn DevOps 2024+: 1 lệnh = 1 hành động rõ ràng.
#
# Quickstart:
#   make help          # xem tất cả lệnh
#   make up-all        # demo thuyết trình (mọi thứ)
#   make health        # check trạng thái các service
#
# Profiles trong docker-compose.yml:
#   infra  → MySQL, MinIO, Kafka, Iceberg-REST (4 services hạ tầng)
#   app    → backend, frontend (cần infra chạy trước, sẽ tự start)
#   all    → cả 6 services
#
# IMPORTANT: `make down` KHÔNG xóa data. Data chỉ mất khi `make nuke` (cẩn thận!).

PROFILE_INFRA := --profile infra
PROFILE_APP  := --profile app
PROFILE_ALL  := --profile all

# Trên Windows PowerShell, dùng `docker compose` (v2). Không cần `-it`.
DC := docker compose

.DEFAULT_GOAL := help

.PHONY: help up-infra up-app up-all down down-infra down-app logs logs-infra logs-app ps health rebuild seed nuke clean-volumes

help: ## Xem tất cả lệnh có sẵn
	@echo "Stock Lakehouse Platform — Makefile"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ════════════════════════════════════════════════════════════════════════════
# UP — Khởi động services theo profile
# ════════════════════════════════════════════════════════════════════════════

up-infra: ## Chỉ chạy hạ tầng (MySQL, MinIO, Kafka, Iceberg)
	$(DC) $(PROFILE_INFRA) up -d
	@echo "✓ Infra đang khởi động. Đợi ~30s cho MySQL healthy, rồi 'make health'"

up-app: ## Chạy app (backend + frontend), tự động start infra nếu chưa chạy
	$(DC) $(PROFILE_APP) up -d
	@echo "✓ App đang khởi động. Đợi ~60s cho backend healthy, rồi 'make health'"

up-all: ## Chạy tất cả 6 services (mặc định cho demo thuyết trình)
	$(DC) $(PROFILE_ALL) up -d
	@echo "✓ Full stack đang khởi động. Đợi ~90s rồi 'make health'"

# ════════════════════════════════════════════════════════════════════════════
# DOWN — Tắt services (GIỮ DATA trong named volumes)
# ════════════════════════════════════════════════════════════════════════════

down: ## Tắt TẤT CẢ services (KHÔNG xóa data — an toàn)
	$(DC) $(PROFILE_ALL) down

down-infra: ## Chỉ tắt hạ tầng (giữ data volumes + app vẫn chạy)
	$(DC) $(PROFILE_INFRA) stop

down-app: ## Chỉ tắt backend + frontend (infra + data vẫn nguyên)
	$(DC) $(PROFILE_APP) stop

# ════════════════════════════════════════════════════════════════════════════
# OBSERVE — Xem trạng thái & logs
# ════════════════════════════════════════════════════════════════════════════

ps: ## Liệt kê services đang chạy + status
	$(DC) $(PROFILE_ALL) ps

logs: ## Tail logs tất cả services (Ctrl+C để thoát)
	$(DC) $(PROFILE_ALL) logs -f --tail=100

logs-infra: ## Tail logs chỉ infra
	$(DC) $(PROFILE_INFRA) logs -f --tail=100

logs-app: ## Tail logs chỉ backend + frontend
	$(DC) $(PROFILE_APP) logs -f --tail=100

health: ## Check health endpoint tất cả services (curl nhanh)
	@echo "═══ Backend (FastAPI :8000) ═══"
	@curl.exe -fsS http://localhost:8000/api/v1/health || echo "  ✗ Backend DOWN"
	@echo ""
	@echo "═══ Frontend (nginx :8081) ═══"
	@curl.exe -fsS -o /dev/null -w "  HTTP %{http_code} (size %{size_download} bytes)\n" http://localhost:8081/ || echo "  ✗ Frontend DOWN"
	@echo ""
	@echo "═══ MinIO API (:9000) ═══"
	@curl.exe -fsS http://localhost:9000/minio/health/live -o /dev/null -w "  HTTP %{http_code}\n" || echo "  ✗ MinIO DOWN"
	@echo ""
	@echo "═══ MySQL (:3307) ═══"
	@docker exec stock-lakehouse-mysql mysqladmin ping -h 127.0.0.1 -uroot -p123456 2>/dev/null && echo "  ✓ MySQL OK" || echo "  ✗ MySQL DOWN"
	@echo ""
	@echo "═══ Docker Compose services ═══"
	@$(DC) $(PROFILE_ALL) ps --format "table {{.Service}}\t{{.State}}\t{{.Status}}"

# ════════════════════════════════════════════════════════════════════════════
# BUILD — Rebuild images (ví dụ: sau khi sửa backend code)
# ════════════════════════════════════════════════════════════════════════════

rebuild: ## Rebuild + restart chỉ app (backend, frontend)
	$(DC) $(PROFILE_APP) up -d --build
	@echo "✓ App rebuilt. 'make health' để verify."

rebuild-all: ## Rebuild + restart toàn bộ stack
	$(DC) $(PROFILE_ALL) up -d --build

# ════════════════════════════════════════════════════════════════════════════
# DANGER ZONE — Các lệnh PHÁ HOẠI, dùng cẩn thận!
# ════════════════════════════════════════════════════════════════════════════

clean-volumes: ## ⚠ Xóa anonymous volumes KHÔNG dùng (giữ named volumes có data)
	$(DC) $(PROFILE_ALL) down --remove-orphans
	@docker volume prune -f
	@echo "✓ Anonymous volumes đã xóa. Named volumes (mysql_data, minio_data, ...) AN TOÀN."

nuke: ## ⚠⚠⚠ XÓA TẤT CẢ — bao gồm data (MySQL, MinIO, Kafka, Iceberg). KHÔNG DÙNG nếu không chắc!
	@echo "⚠ CẢNH BÁO: lệnh này sẽ XÓA TẤT CẢ DATA trong MySQL, MinIO, Kafka, Iceberg."
	@echo "Nhấn Ctrl+C trong 5 giây để hủy..."
	@timeout 5 > nul 2>&1
	$(DC) $(PROFILE_ALL) down -v --remove-orphans
	@docker volume prune -f
	@echo "✗ Tất cả data đã xóa."