# MapGTA

9 bộ bản đồ, mỗi bộ gồm 6 ô và 1 LOD. Hai bộ Việt Nam là `postalvn`
(Postal VN) và `vietnam` (Việt Nam). Mặc định khởi tạo của GTA5VN là `postalvn`.

## Sửa texture ngày 2026-09-25

Đã chuẩn hóa tên texture bên trong 8 YTD cùng hash trong dictionary:

- 6 ô `postalvn`: các tên `minimap_* (1)`, `minimap_2_0 (2)` và `minimap_2_1`
  thành đúng `minimap_sea_<hàng>_<cột>` như tên file.
- LOD của `postal` và `postalv2`: `minimap_sea_lod_128` thành `minimap_lod_128`.

Toàn bộ dữ liệu ảnh và mipmap giữ nguyên từng byte. File RSC7 giữ nguyên header,
kích thước các vùng và con trỏ; chỉ sửa chuỗi tên, hash tra cứu và nén lại.
Nguồn trước sửa: commit `594647dbcffec3df69518d59316df6dfa0351af3`.
`assets-manifest.json` lưu SHA-256 file và riêng vùng graphics để kiểm tra.

```powershell
python tools/check-textures.py
```

`--fix` chỉ sửa các tên lệch đã biết, kiểm tra toàn bộ trước khi ghi và tự sao lưu
file gốc sang `MapGTA-backup-<thời gian>` cạnh repo. Chạy lại không thay đổi YTD
đã chuẩn hóa. Công cụ dùng Python standard library; không cần Pillow.

## GTA5VN

Đây là repo asset. Streaming, lựa chọn mặc định, lưu lựa chọn và Vue UI thuộc
`NovatisCity/FXSource/resources/[codev]/gta5vn_mainmenu`, không cần `eki_map`.
Tại thư mục resource đó, đồng bộ từ repo đã kiểm tra bằng:

```powershell
python tools/update-map-assets.py --source 'D:\DecryptServer\MapGTA'
pnpm --dir web build
python tools/check-map-assets.py
lua tools/check-mapstyles.lua
pnpm --dir web test:mapstyles
```

Lần đầu nhận phiên bản mặc định `mapgta-postalvn-1`, người chơi cũ và mới đều
khởi tạo `postalvn`. Sau đó lựa chọn cá nhân được giữ qua reconnect/restart;
nút **Mặc định** trở về Postal VN. Lưu trên thiết bị bằng KVP của main menu.

Thay đổi hiện ở local; chưa push GitHub hay restart server. Cần kiểm tra thực tế
trong FiveM với cache lạnh, lần mở pause map đầu tiên, pan/zoom và đổi cả 9 bộ.
