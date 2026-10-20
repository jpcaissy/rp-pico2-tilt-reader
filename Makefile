MP = mpremote
NPROC = $(nproc)

.PHONY: run deploy repl ls reset clean micropython

# Run main.py from your machine without saving it to the board
run:
	$(MP) run app/app.py

# Copy everything in app/ to the board and reboot so main.py starts
deploy:
	$(MP) cp -r app/*.py. : + reset

# Interactive REPL (Ctrl-] to exit)
repl:
	$(MP) repl

# List files on the board
ls:
	$(MP) fs ls

# Soft-reset the board
reset:
	$(MP) reset

micropython:
	make -C micropython/ports/rp2 BOARD=RPI_PICO2_W clean # just to make sure we have a fresh state
	make -C micropython/ports/rp2 BOARD=RPI_PICO2_W submodules
	make -C micropython/ports/rp2 BOARD=RPI_PICO2_W -j$(NPROC)
	cp micropython/ports/rp2/build-RPI_PICO2_W/firmware.uf2 ./firmware.uf2
	echo "Built: ./firmware.uf2"
