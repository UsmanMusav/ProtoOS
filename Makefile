PYTHON ?= python3
VERSION ?= 0.1.2
ISO := dist/ProtoOS-$(VERSION)-x86_64.iso

.PHONY: all iso check clean

all: iso

iso:
	$(PYTHON) tools/build.py --output $(ISO)

check: iso
	$(PYTHON) tools/verify_iso.py $(ISO)

clean:
	rm -rf build dist
