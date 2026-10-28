include("$(PORT_DIR)/boards/manifest.py")   # keep the standard rp2 frozen modules
require("umqtt.simple")
module("app.py", base_path="$(MPY_DIR)/../app")
module("ble_scan.py", base_path="$(MPY_DIR)/../app")
# exclude config.py from the manifest and have it copied to the fs
# module("config.py", base_path="$(MPY_DIR)/../app")
module("mqtt.py", base_path="$(MPY_DIR)/../app")
module("oled.py", base_path="$(MPY_DIR)/../app")
module("wifi.py", base_path="$(MPY_DIR)/../app")
