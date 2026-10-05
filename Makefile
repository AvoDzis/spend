AGENT := com.spend.month-report
PLIST := $(HOME)/Library/LaunchAgents/$(AGENT).plist
LOG := $(HOME)/Library/Logs/spend-report.log
SYNC := com.spend.sync
SYNC_PLIST := $(HOME)/Library/LaunchAgents/$(SYNC).plist
SYNC_LOG := $(HOME)/Library/Logs/spend-sync.log

test:
	python3 -m unittest discover -s tests -t .

install:
	mkdir -p ~/.local/bin && ln -sf $(CURDIR)/bin/spend ~/.local/bin/spend

# Background jobs (LaunchAgents): email last month's report on the 1st at 10:00, and every 30 min
# import phone lines + refresh the iPhone widget's data.   make schedule EMAIL=you@gmail.com
schedule:
	@test -n "$(EMAIL)" || { echo "usage: make schedule EMAIL=you@gmail.com"; exit 2; }
	mkdir -p $(dir $(PLIST)) $(dir $(LOG))
	sed -e 's|@REPO@|$(CURDIR)|g' -e 's|@EMAIL@|$(EMAIL)|g' -e 's|@LOG@|$(LOG)|g' scripts/month-report.plist > $(PLIST)
	sed -e 's|@REPO@|$(CURDIR)|g' -e 's|@LOG@|$(SYNC_LOG)|g' scripts/sync.plist > $(SYNC_PLIST)
	-launchctl bootout gui/$$(id -u)/$(AGENT) 2>/dev/null
	-launchctl bootout gui/$$(id -u)/$(SYNC) 2>/dev/null
	launchctl bootstrap gui/$$(id -u) $(PLIST)
	launchctl bootstrap gui/$$(id -u) $(SYNC_PLIST)
	@echo "scheduled: report on the 1st at 10:00 → $(EMAIL) (log: $(LOG)); sync every 30 min (log: $(SYNC_LOG))"

unschedule:
	-launchctl bootout gui/$$(id -u)/$(AGENT) 2>/dev/null
	-launchctl bootout gui/$$(id -u)/$(SYNC) 2>/dev/null
	rm -f $(PLIST) $(SYNC_PLIST)

.PHONY: test install schedule unschedule
