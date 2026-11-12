PYTHON ?= python3
VERSION ?= 0.1.3
ISO := dist/ProtoOS-$(VERSION)-x86_64.iso
HYPERV_VHD := dist/ProtoOS-HyperV-0.2.2.vhd

.PHONY: all iso check vhd check-vhd clean

all: iso

iso:
	$(PYTHON) tools/build.py --output $(ISO)

check: iso
	$(PYTHON) tools/verify_iso.py $(ISO)

vhd:
	$(PYTHON) tools/build_hyperv_vhd.py --output $(HYPERV_VHD)

check-vhd: vhd
	$(PYTHON) tools/verify_hyperv_vhd.py $(HYPERV_VHD)

clean:
	rm -rf build dist
