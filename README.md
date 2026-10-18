# SCIO Lunch Order

This is a simple python app that automates weekly ordering of school lunches on
the school site which forces parents to order lunches every week manually.

The HTTP server returns ASP.NET HTML pages.

## Status

The app logs in, reads the weekly menu and prints it, and orders one dish for
one day per run. Cancelling an order is not supported yet.

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


## Development

```sh
.venv/bin/python -m pytest
```

The tests need neither the network nor a browser: the parser runs against the
saved pages in `tests/data`, and the login and order sequences run against a
stub page (`tests/fake_site.py`) that mimics the postback behaviour of the site.

```
src/scio_lunch_order/
    browser.py   Playwright session: open, log in, hand over the page HTML
    parser.py    warea markup -> models, dialog and popup texts
    models.py    Menu / Day / MenuOption / FoodItem / Action / OrderResult
    selection.py --day / --item -> the dish to order
    render.py    text output
    cli.py       argument parsing, JSON output
```

## Manual process

1. Go to the site https://skola.czszlin.cz:4434/iorders/ - you are not logged
2. Click the element a id=cmdLoginUser - it actually uses href=javascript
3. Wait until the page re-renders and the element `span` with `id="lblUserSpec"` appears
3. Fill the element input id=txtLoginA with user name
3. Fill the element input id=txtLoginB with password
5. Click the element a id=cmdLogin - it actually uses href=javascript

## Ordering

1. Click the button labeled with "Objednat" on the menu item line. The order
   button's id is like
   `repeaterDays_ctl${day index}_repeaterFoodType_ctl${day item index}_repeaterFood_ctl00_btnFood`.
   The indexes are positions on the current page, so the app clicks the id it
   has just parsed instead of building one.
2. Wait until the dialog panel appears - it is a div element with the id
   `dialogPanel` and contains the button with the id `btnDialogYes`. The
   question in `.paneldlg__msg` names the dish and the date:
   `Opravdu si přejete objednat rybí nugetky … dne pátek 16. října 2026, …?`
3. Clicking `btnDialogYes` reloads the menu with a popup: the div element with
   the id `infoPanel` (`Vaše objednávka byla úspěšně provedena`), which a script
   hides by setting the css style display to 'none'.
4. An ordered dish keeps its `Objednat` button and gets a `Zrušit objednávku`
   button next to it.

## Page structure description

- The menu is stored in the element: `<div class="warea">` which is present if you are not logged in
- Day starts with: `<div class="fday bobt boto">`
- Day can contains menu options:
    - Header: `<div class="fheader bobot boto">`
    - Followed by contents: `<div class="fblock">`
- Day menu description is stored in the element: `<div class="food--label">`
- An ordered item is marked by the element `a` with the text `Zrušit objednávku`
- The order activity is done by clicking the element `a` with the text `Objednat`


## Sample warea content

```html
<div class="warea">
<div class="fday bobt boto">zítra,  21. září<a href="#" id="mnu21.09.2026 0:00:00">
</a>
</div>
<div class="fheader bobt boto">
<div class="ftype">Oběd 3</div>
<div class="fheader--soupl">
<img src="images/soup.png" alt="soup" style="height:14px;width:14px;margin:2px 5px 0;">Polévka vývar s nudlemi a zeleninou (3,9)</div>
</div>
<div class="fblock">
<div class="frowinfo">&nbsp; <div class="finfo__count">&nbsp;</div>
<div class="finfo__state">
<img src="./images/greenpoint.png" width="15" height="15" title="Objednáno">
</div>
</div>
<div class="fdatashort">
<div class="fdata__nmb">3.</div>
<div class="fdata__detail">
<div class="food__detail">
<div class="food--label">Vepřové maso po námořnicku (rajský protlak, vejce) (lepek 1.1,3), těstoviny 1,3<span class="allergen itemallergen"> (1-lepek)</span>
</div>
</div>
</div>
</div>
<div class="fcmd">
<div class="mfrowinfo mfdata__single">&nbsp; <div class="finfo__count">&nbsp;</div>
<div class="finfo__state">
<img src="./images/greenpoint.png" width="15" height="15" title="Objednáno">
</div>
</div>
<a id="repeaterDays_ctl00_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood" class="button tbutton tbutton1" href="javascript:__doPostBack('repeaterDays$ctl00$repeaterFoodType$ctl00$repeaterFood$ctl00$btnFood','')">Objednat</a>
<a id="repeaterDays_ctl00_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood2" class="button tbutton tbutton2" href="javascript:__doPostBack('repeaterDays$ctl00$repeaterFoodType$ctl00$repeaterFood$ctl00$btnFood2','')">Zrušit objednávku</a>
</div>
</div>
<div class="fday bobt boto">úterý 22. září<a href="#" id="mnu22.09.2026 0:00:00">
</a>
</div>
<div class="fheader bobt boto">
<div class="ftype">Oběd 3</div>
<div class="fheader--soupl">
<img src="images/soup.png" alt="soup" style="height:14px;width:14px;margin:2px 5px 0;">Polévka čočková<span class="allergen itemallergen"> (1-lepek)</span>
</div>
</div>
<div class="fblock">
<div class="frowinfo">&nbsp; <div class="finfo__count">&nbsp;</div>
<div class="finfo__state">
<img src="./images/greenpoint.png" width="15" height="15" title="Objednáno">
</div>
</div>
<div class="fdatashort">
<div class="fdata__nmb">3.</div>
<div class="fdata__detail">
<div class="food__detail">
<div class="food--label">Soukenický řízek - mleté maso se sýrem, smažený v trojobalu 1,3,7, bramborová kaše 7<span class="allergen itemallergen"> (7-mléko)</span>, kompot</div>
</div>
</div>
</div>
<div class="fcmd">
<div class="mfrowinfo mfdata__single">&nbsp; <div class="finfo__count">&nbsp;</div>
<div class="finfo__state">
<img src="./images/greenpoint.png" width="15" height="15" title="Objednáno">
</div>
</div>
<a id="repeaterDays_ctl01_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood" class="button tbutton tbutton1" href="javascript:__doPostBack('repeaterDays$ctl01$repeaterFoodType$ctl00$repeaterFood$ctl00$btnFood','')">Objednat</a>
<a id="repeaterDays_ctl01_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood2" class="button tbutton tbutton2" href="javascript:__doPostBack('repeaterDays$ctl01$repeaterFoodType$ctl00$repeaterFood$ctl00$btnFood2','')">Zrušit objednávku</a>
</div>
</div>
<div class="fday bobt boto">středa 23. září<a href="#" id="mnu23.09.2026 0:00:00">
</a>
</div>
<div class="fheader bobt boto">
<div class="ftype">Oběd 3</div>
<div class="fheader--soupl">
<img src="images/soup.png" alt="soup" style="height:14px;width:14px;margin:2px 5px 0;">Polévka frankfurtská(1)</div>
</div>
<div class="fblock">
<div class="frowinfo">&nbsp; <div class="finfo__count">&nbsp;</div>
<div class="finfo__state">
<img src="./images/greenpoint.png" width="15" height="15" title="Objednáno">
</div>
</div>
<div class="fdatashort">
<div class="fdata__nmb">3.</div>
<div class="fdata__detail">
<div class="food__detail">
<div class="food--label">Kuřecí prsní maso na kari 1,7,9, dušená rýže</div>
</div>
</div>
</div>
<div class="fcmd">
<div class="mfrowinfo mfdata__single">&nbsp; <div class="finfo__count">&nbsp;</div>
<div class="finfo__state">
<img src="./images/greenpoint.png" width="15" height="15" title="Objednáno">
</div>
</div>
<a id="repeaterDays_ctl02_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood" class="button tbutton tbutton1" href="javascript:__doPostBack('repeaterDays$ctl02$repeaterFoodType$ctl00$repeaterFood$ctl00$btnFood','')">Objednat</a>
<a id="repeaterDays_ctl02_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood2" class="button tbutton tbutton2" href="javascript:__doPostBack('repeaterDays$ctl02$repeaterFoodType$ctl00$repeaterFood$ctl00$btnFood2','')">Zrušit objednávku</a>
</div>
</div>
<div class="fheader bobt boto">
<div class="ftype">Oběd 6</div>
<div class="fheader--soupl">
<img src="images/soup.png" alt="soup" style="height:14px;width:14px;margin:2px 5px 0;">Polévka frankfurtská(1)</div>
</div>
<div class="fblock">
<div class="frowinfo">&nbsp;       </div>
<div class="fdatalong">
<div class="fdata__nmb">6.</div>
<div class="fdata__detail">
<div class="food__detail">
<div class="food--label">Játrová omáčka(1), dušená rýže</div>
</div>
</div>
</div>
<div class="fcmd">
<div class="mfrowinfo mfdata__single">&nbsp;       </div>
<a id="repeaterDays_ctl02_repeaterFoodType_ctl01_repeaterFood_ctl00_btnFood" class="button tbutton tbutton1" href="javascript:__doPostBack('repeaterDays$ctl02$repeaterFoodType$ctl01$repeaterFood$ctl00$btnFood','')">Objednat</a>
</div>
</div>
<div class="fday bobt boto">čtvrtek 24. září<a href="#" id="mnu24.09.2026 0:00:00">
</a>
</div>
<div class="fheader bobt boto">
<div class="ftype">Oběd 3</div>
<div class="fheader--soupl">
<img src="images/soup.png" alt="soup" style="height:14px;width:14px;margin:2px 5px 0;">Polévka rybí se zeleninou a opečeným rohlíkem(1,1.4,9,7)</div>
</div>
<div class="fblock">
<div class="frowinfo">&nbsp; <div class="finfo__count">&nbsp;</div>
<div class="finfo__state">
<img src="./images/greenpoint.png" width="15" height="15" title="Objednáno">
</div>
</div>
<div class="fdatashort">
<div class="fdata__nmb">3.</div>
<div class="fdata__detail">
<div class="food__detail">
<div class="food--label">Bramborový knedlík plněný uzeným masem, zelí 1,3,9,7</div>
</div>
</div>
</div>
<div class="fcmd">
<div class="mfrowinfo mfdata__single">&nbsp; <div class="finfo__count">&nbsp;</div>
<div class="finfo__state">
<img src="./images/greenpoint.png" width="15" height="15" title="Objednáno">
</div>
</div>
<a id="repeaterDays_ctl03_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood" class="button tbutton tbutton1" href="javascript:__doPostBack('repeaterDays$ctl03$repeaterFoodType$ctl00$repeaterFood$ctl00$btnFood','')">Objednat</a>
<a id="repeaterDays_ctl03_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood2" class="button tbutton tbutton2" href="javascript:__doPostBack('repeaterDays$ctl03$repeaterFoodType$ctl00$repeaterFood$ctl00$btnFood2','')">Zrušit objednávku</a>
</div>
</div>
<div class="fheader bobt boto">
<div class="ftype">Oběd 6</div>
<div class="fheader--soupl">
<img src="images/soup.png" alt="soup" style="height:14px;width:14px;margin:2px 5px 0;">Polévka rybí se zeleninou a opečeným rohlíkem(1,1.4,9,7)</div>
</div>
<div class="fblock">
<div class="frowinfo">&nbsp;       </div>
<div class="fdatalong">
<div class="fdata__nmb">6.</div>
<div class="fdata__detail">
<div class="food__detail">
<div class="food--label">Cizrnový salát se zeleninou, balkánským sýrem, pečivo (studený) (1,7)</div>
</div>
</div>
</div>
<div class="fcmd">
<div class="mfrowinfo mfdata__single">&nbsp;       </div>
<a id="repeaterDays_ctl03_repeaterFoodType_ctl01_repeaterFood_ctl00_btnFood" class="button tbutton tbutton1" href="javascript:__doPostBack('repeaterDays$ctl03$repeaterFoodType$ctl01$repeaterFood$ctl00$btnFood','')">Objednat</a>
</div>
</div>
<div class="fday bobt boto">pátek 25. září<a href="#" id="mnu25.09.2026 0:00:00">
</a>
</div>
<div class="fheader bobt boto">
<div class="ftype">Oběd 3</div>
<div class="fheader--soupl">
<img src="images/soup.png" alt="soup" style="height:14px;width:14px;margin:2px 5px 0;">Polévka z pečené mrkve s čerstvým koriandrem  1,7,9<span class="allergen itemallergen"> (1-lepek)</span>
</div>
</div>
<div class="fblock">
<div class="frowinfo">&nbsp; <div class="finfo__count">&nbsp;</div>
<div class="finfo__state">
<img src="./images/greenpoint.png" width="15" height="15" title="Objednáno">
</div>
</div>
<div class="fdatashort">
<div class="fdata__nmb">3.</div>
<div class="fdata__detail">
<div class="food__detail">
<div class="food--label">Dušený špenát, vařené vejce 1,3,7<span class="allergen itemallergen"> (1-lepek, 3-vejce)</span>, vařený brambor 7</div>
</div>
</div>
</div>
<div class="fcmd">
<div class="mfrowinfo mfdata__single">&nbsp; <div class="finfo__count">&nbsp;</div>
<div class="finfo__state">
<img src="./images/greenpoint.png" width="15" height="15" title="Objednáno">
</div>
</div>
<a id="repeaterDays_ctl04_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood" class="button tbutton tbutton1" href="javascript:__doPostBack('repeaterDays$ctl04$repeaterFoodType$ctl00$repeaterFood$ctl00$btnFood','')">Objednat</a>
<a id="repeaterDays_ctl04_repeaterFoodType_ctl00_repeaterFood_ctl00_btnFood2" class="button tbutton tbutton2" href="javascript:__doPostBack('repeaterDays$ctl04$repeaterFoodType$ctl00$repeaterFood$ctl00$btnFood2','')">Zrušit objednávku</a>
</div>
</div>
<div class="fheader bobt boto">
<div class="ftype">Oběd 6</div>
<div class="fheader--soupl">
<img src="images/soup.png" alt="soup" style="height:14px;width:14px;margin:2px 5px 0;">Polévka z pečené mrkve s čerstvým koriandrem  1,7,9<span class="allergen itemallergen"> (1-lepek)</span>
</div>
</div>
<div class="fblock">
<div class="frowinfo">&nbsp;       </div>
<div class="fdatalong">
<div class="fdata__nmb">6.</div>
<div class="fdata__detail">
<div class="food__detail">
<div class="food--label">Dušený špenát, vepřový vrabec 1,7, vařený brambor 7</div>
</div>
</div>
</div>
<div class="fcmd">
<div class="mfrowinfo mfdata__single">&nbsp;       </div>
<a id="repeaterDays_ctl04_repeaterFoodType_ctl01_repeaterFood_ctl00_btnFood" class="button tbutton tbutton1" href="javascript:__doPostBack('repeaterDays$ctl04$repeaterFoodType$ctl01$repeaterFood$ctl00$btnFood','')">Objednat</a>
</div>
</div>
</div>
```
