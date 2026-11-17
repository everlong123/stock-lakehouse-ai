# Ghi chú vận hành — giải phóng RAM sau khi dừng WSL/Docker

> **Đo ngày 06/11/2026** trên máy 32 GB RAM, Windows 11 + WSL2 (Ubuntu-24.04 + docker-desktop).

## Vì sao máy bị "nặng" sau khi dừng stack

Ba nguyên nhân độc lập cùng tồn tại trên máy này:

### 1. `vmmemWSL` giữ RAM sau khi đóng distro (nguyên nhân chính)

Khi WSL2 chạy, RAM của host được WSL giữ trong một tiến trình tên `vmmemWSL`.
Dù distro báo `Stopped`, tiến trình này có thể **vẫn còn** và giữ tới hàng chục GB.

Đã ghi trong `~/.wslconfig`:

```ini
memory=8GB          # trần cứng cho VM
swap=4GB
autoMemoryReclaim=dropcache   # trả page cache của guest về host khi rảnh
vmIdleTimeout=-1             # KHÔNG tự tắt VM khi rảnh
```

`autoMemoryReclaim=dropcache` là chốt chặn quan trọng: trước đó `vmmemWSL` giữ
14.3 GB trong khi guest thực tế chỉ dùng ~2.8 GB — phần còn lại là buff/cache
đọc từ file parquet mà WSL không chịu trả lại.

**Kiểm tra:**
```powershell
wsl.exe -l -v                    # cột STATE phải là Stopped
Get-Process vmmemWSL            # không được có output
wsl.exe --shutdown              # tắt triệt để, giải phóng vmmemWSL
```

### 2. Standby cache của Windows (~18 GB)

Đây là nguyên nhân **ít ai để ý**: Windows giữ RAM đã đọc từ đĩa trong
*standby list*. Task Manager báo là "đang dùng" nhưng thực tế rảnh, và
**Windows không chịu trả** cho tới khi có áp lực bộ nhớ.

Đo được sau khi tắt WSL: **standby cache 17–18.5 GB** trong khi tổng RAM chỉ
31.8 GB — tức là hơn một nửa RAM bị "cache" và không dùng được ngay.

**Cách giải phóng (không cần Administrator):**
```powershell
python scripts/flush_standby_cache.py
```
Script gọi `EmptyWorkingSet` cho mọi process → Windows hạ cache của chúng
xuống standby list (không mất dữ liệu, chỉ tốn thêm vài lần đọc đĩa lần sau).

Đo ngày 06/11/2026: available RAM **18.4 GB → 21.2 GB** sau khi flush.

> **Lưu ý:** `MemoryPurgeStandbyList` (xóa hẳn standby list) **không có** trong
> `advapi32`/`ntdll` trên Windows 11 build này và cần quyền `SE_PROFILE_NAME`
> (Administrator). Script `scripts/purge_standby_list.py` kiểm tra và báo rõ
> nếu không đủ quyền — **không** dùng nó khi chưa cần.

### 3. `swap.vhdx` sót lại trong `%LOCALAPPDATA%\Temp` (4.11 GB đĩa)

Mỗi lần WSL bị kill cưỡng bức (đóng terminal, hết session) để lại một file
`swap.vhdx` trong thư mục Temp. File này **không tự xoá**.

Đo ngày 06/11/2026: **11 file, tổng 4.11 GB** nằm rác.

Dọn (an toàn khi WSL đã `Stopped`):
```powershell
Get-ChildItem "$env:LOCALAPPDATA\Temp" -Filter "swap.vhdx" -Recurse |
    Remove-Item -Force
```

## Thứ KHÔNG nên tắt

| Thành phần | Lý do |
|---|---|
| **MySQL của XAMPP** (`D:\xampp\mysql`, port 3306) | **Không thuộc project này.** Project dùng MySQL trong Docker publish ra `127.0.0.1:3307` (xem `backend/.env.local`). Dừng nó chỉ giải phóng ~200 MB và sẽ phải bật lại khi cần XAMPP. Cần quyền Administrator để `Stop-Service mysql` (hiện service là `Automatic`). |
| **Task `Stock-LH-DailyRefresh`** | Chạy `backend/daily_refresh.py` lúc **06:00 hằng ngày** để đồng bộ dữ liệu thị trường. Tắt nó = dữ liệu trong MinIO sẽ cũ dần. Nếu thầy yêu cầu "dữ liệu phải luôn real", **phải giữ task này**. |
| **WSL vì lý do khác** | `vmIdleTimeout=-1` cố tình giữ VM sống để **không giết Docker Engine** giữa chừng. Nếu VM tự tắt, container mysql/minio chết theo → MinIO trả `connection-refused` → tưởng như dữ liệu bị xoá. Xem giải thích dài trong `~/.wslconfig`. |

> **Cập nhật 10/11/2026:** container `kafka` và `iceberg-rest` đã bị gỡ khỏi
> `docker-compose.yml`, nên danh sách container của project hiện còn **4** service
> thường trực: `mysql`, `minio`, `backend`, `frontend` — cộng thêm `scheduler` khi
> bật profile `app`. Nhờ vậy, phần RAM mà broker Kafka và Iceberg REST catalog từng
> chiếm cũng được giải phóng.

## Thứ tự thao tác khi máy bị nặng

```powershell
# 1. Dừng dev stack
.\stop-all.ps1

# 2. Tắt WSL triệt để (giải phóng vmmemWSL)
wsl.exe --shutdown

# 3. Dọn swap.vhdx rác
Get-ChildItem "$env:LOCALAPPDATA\Temp" -Filter "swap.vhdx" -Recurse | Remove-Item -Force

# 4. Đẩy standby cache về cho RAM
python scripts/flush_standby_cache.py

# 5. Kiểm tra
Get-Process vmmemWSL                    # phải rỗng
Get-Counter "\Memory\Standby Cache Normal Priority Bytes"
```

## Số đo

| Mục | Trước (06/11/2026) | Sau |
|---|---|---|
| Available RAM | 17.3 GB | **21.2 GB** |
| RAM đang dùng (Task Manager) | 14.5 GB (46%) | **11.6 GB (36%)** |
| `vmmemWSL` | Có (giữ hàng chục GB) | **Không còn** |
| `swap.vhdx` rác | 11 file / 4.11 GB | **0 file** |
| Đĩa C trống | 25.6 GB | **29.7 GB** |

## Quy trình vận hành (đã đặt trong `stop-all.ps1`)

`stop-all.ps1` hiện **chỉ** dừng tiến trình dev (backend + frontend), giữ
Docker containers để lần sau khởi động nhanh. Các bước 2–4 ở trên nên chạy
thủ công khi máy thực sự bị nặng, hoặc dùng:

```powershell
.\stop-all.ps1 -All      # dev + docker containers + WSL
.\stop-all.ps1 -Wsl      # chỉ tắt WSL (giải phóng vmmemWSL + RAM)
```
