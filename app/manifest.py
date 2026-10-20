include("$(PORT_DIR)/boards/manifest.py")   # keep the standard rp2 frozen modules
module("app.py", base_path="$(MPY_DIR)/../app")
module("oled.py", base_path="$(MPY_DIR)/../app")
module("ble_scan.py", base_path="$(MPY_DIR)/../app")
module("wifi.py", base_path="$(MPY_DIR)/../app")
