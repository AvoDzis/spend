test:
	python3 -m unittest discover -s tests -t .

install:
	mkdir -p ~/.local/bin && ln -sf $(CURDIR)/bin/spend ~/.local/bin/spend

.PHONY: test install
