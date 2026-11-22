# SCIO Lunch Order

This is a simple python app that automates weekly ordering of school lunches on
the school site which forces parents to order lunches every week manually.

The HTTP server returns ASP.NET HTML pages.

## Status

The app logs in, reads the weekly menu and prints it, orders one dish for one
day, or orders every day of the menu in one run. It cancels the order of one
day, or every order of the menu.

## Installation

```sh
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/playwright install chromium
```

Chromium also needs a handful of system libraries. On AlmaLinux / RHEL 10:

```sh
sudo dnf install nss nspr atk at-spi2-atk cups-libs libdrm libxkbcommon \
    libXcomposite libXdamage libXfixes libXrandr mesa-libgbm alsa-lib libxcb
```

On Debian / Ubuntu `.venv/bin/playwright install --with-deps chromium` installs
them for you.

## Usage

```sh
export SCIO_LUNCH_USER=jmeno
export SCIO_LUNCH_PASSWORD=heslo      # optional, otherwise it asks
.venv/bin/scio-lunch
```

```
Jídelníček: 5 dnů, 8 položek, 5 objednáno

středa 23. září                                                     2026-09-23
------------------------------------------------------------------------------
    Oběd 3
        polévka: Polévka frankfurtská(1)
    [x] 3. Kuřecí prsní maso na kari 1,7,9, dušená rýže

    Oběd 6
        polévka: Polévka frankfurtská(1)
    [ ] 6. Játrová omáčka(1), dušená rýže
```

`[x]` is an ordered dish, `[ ]` one that can still be ordered.

Useful options:

| option | meaning |
| --- | --- |
| `--json` | machine readable output, including the button ids |
| `--from-file PATH` | parse a saved page instead of logging in (no browser, no password) |
| `--save-html PATH` | keep the downloaded page, e.g. as a new test fixture |
| `--headed`, `--slow-mo MS` | watch the browser do the work |
| `--pause SECONDS` | average pause before every click (default 2, each pause 0.5-1.5x of it) |
| `--screenshot PATH` | save a screenshot of the menu page |
| `--insecure` | accept an invalid HTTPS certificate |
| `-v` | log every step to stderr |

Try it without any credentials:

```sh
.venv/bin/scio-lunch --from-file sample.html
```

### Usage: order

```sh
export SCIO_LUNCH_USER=jmeno
export SCIO_LUNCH_PASSWORD=heslo      # optional, otherwise it asks
.venv/bin/scio-lunch order --day "pátek 16. října" --item 3
```

```
Objednáno: pátek 16. října (2026-10-16)
    3. Rybí nugetky z tresky (1,4,3), bramborová kaše 7
    Vaše objednávka byla úspěšně provedena
Stav účtu: 1 700 Kč → 1 600 Kč
```

- `--day` is `2026-10-16`, `16.10.2026` or a label like `pátek 16. října` /
  `16. října` (diacritics optional). A label is matched by its date, so
  `úterý 13. října` finds the day the site calls `zítra, 13. října`; a weekday
  that does not fit the date is an error.
- `--item` is the dish number shown in the menu (`3`, `6`, ...).
- `--dry-run` logs in and finds the dish, but does not order it. With
  `--from-file` nothing is ordered either.
- A dish that is already ordered is left alone (exit code 0); its `Objednat`
  link is still on the page and clicking it again would most likely order a
  second portion.
- If another dish of that day is ordered, the command refuses (exit code 1).
- The site's confirmation dialog must name the requested date, otherwise it is
  not answered.
- After the order the menu is read again; the run fails unless the dish is
  marked as ordered.

All the options listed above (`--json`, `--headed`, ...) work with `order` too.

### Usage: order all

```sh
.venv/bin/scio-lunch order-all
```

```
čtvrtek 15. října (2026-10-15) -- vyberte jídlo:
    3. Bulgur se sýrem Halloumi, zeleninou (teplý pokrm) 1,7
    6. Kynuté knedlíky s povidly, sypané perníkem (1,3,7)
Číslo jídla (3, 6), Enter = nic: 6
...
Celý jídelníček: objednáno: 6, už bylo objednáno: 2, přeskočeno: 1

Už bylo objednáno: zítra, 13. října (2026-10-13)
    3. Těstovinový salát s drůbežím masem, brokolicí, sýrem (teplý) 1,3,7,9
...
Objednáno: čtvrtek 15. října (2026-10-15)
    6. Kynuté knedlíky s povidly, sypané perníkem (1,3,7)
...
Stav účtu: 1 700 Kč → 1 100 Kč
```

- A day that has a dish ordered is left alone.
- A day with a single dish gets it without asking.
- For a day with more dishes you are asked which one; Enter orders nothing
  that day. The questions go to stderr, so `--json` output stays clean.
- All questions come first, the site is not touched while you decide. If it
  logged you out meanwhile, the app logs in again before ordering.
- The days are then ordered strictly one after another, at a human pace (see
  `--pause`), each one from the menu page the previous order ended on.
- A failure of the site (no dialog, no confirmation, dish not marked as
  ordered) stops the run: the remaining days are reported as skipped, and the
  exit code is 1. A day that changed meanwhile (e.g. ordered on the site) fails
  alone.
- Without a terminal (e.g. from cron) nobody can be asked: days with more
  dishes are skipped with a warning, the others are ordered.
- `--dry-run` asks, but orders nothing; so does `--from-file`.

The choice is made by a *chooser* (`choosers.py`): a function that gets the
day and its dishes and returns one of them, or `None`. Only the interactive
one exists now; a list of preferred dishes or an AI deciding between meat and
vegetarian are meant to be further choosers.

### Usage: cancel

```sh
.venv/bin/scio-lunch cancel --day "pondělí 23. listopadu"
```

```
Zrušeno: zítra, 23. listopadu (2026-11-23)
    3. Bratislavské vepřové plecko /maso kostičky/ s hráškem, mrkví, smetanou
      1,7,9, těstoviny 1,3
    Vaše objednávka byla zrušena
Stav účtu: 1 600 Kč → 1 700 Kč
```

- `--day` works as for `order`. The dish ordered that day is cancelled.
- `--item` is needed only if more dishes of the day are ordered; otherwise the
  command refuses (exit code 1).
- A day (or `--item`) with nothing ordered is left alone (exit code 0).
- An ordered dish without the `Zrušit objednávku` link (e.g. after the
  deadline) cannot be cancelled (exit code 1).
- The site's dialog must be headed `Zrušení objednávky` and name the requested
  date, otherwise it is not answered.
- After the cancellation the menu is read again; the run fails unless the dish
  is no longer marked as ordered.
- `--dry-run` logs in and finds the dish, but does not cancel it; so does
  `--from-file`.

### Usage: cancel all

```sh
.venv/bin/scio-lunch cancel-all --dry-run    # see what would be cancelled
.venv/bin/scio-lunch cancel-all
```

```
Celý jídelníček: zrušeno: 4, nebylo objednáno: 1

Nebylo objednáno: zítra, 23. listopadu (2026-11-23)

Zrušeno: úterý 24. listopadu (2026-11-24)
    3. Taštičky z bramborového těsta plněné povidly, strouhaný tvaroh 1,7,8,9
...
Stav účtu: 1 700 Kč → 2 100 Kč
```

- Every ordered dish of the menu is cancelled. Nothing is asked, so try
  `--dry-run` first.
- An order that cannot be cancelled any more is skipped.
- The dishes are cancelled strictly one after another, at a human pace, like
  `order-all` orders them; the first failure of the site stops the run and the
  exit code is 1.

## Development

Please consult [HACKING.md](./HACKING.md).
Pull requests are more then welcome!
