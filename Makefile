AGENT := com.spend.month-report
PLIST := $(HOME)/Library/LaunchAgents/$(AGENT).plist
LOG := $(HOME)/Library/Logs/spend-report.log

test:
	python3 -m unittest discover -s tests -t .

install:
	mkdir -p ~/.local/bin && ln -sf $(CURDIR)/bin/spend ~/.local/bin/spend

# Email last month's report on the 1st of every month at 10:00: make schedule EMAIL=you@gmail.com
schedule:
	@test -n "$(EMAIL)" || { echo "usage: make schedule EMAIL=you@gmail.com"; exit 2; }
	mkdir -p $(dir $(PLIST)) $(dir $(LOG))
	sed -e 's|@REPO@|$(CURDIR)|g' -e 's|@EMAIL@|$(EMAIL)|g' -e 's|@LOG@|$(LOG)|g' scripts/month-report.plist > $(PLIST)
	-launchctl bootout gui/$$(id -u)/$(AGENT) 2>/dev/null
	launchctl bootstrap gui/$$(id -u) $(PLIST)
	@echo "scheduled: 1st of every month at 10:00 → $(EMAIL) (log: $(LOG))"

unschedule:
	-launchctl bootout gui/$$(id -u)/$(AGENT) 2>/dev/null
	rm -f $(PLIST)

.PHONY: test install schedule unschedule
