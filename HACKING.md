# Development

```sh
.venv/bin/python -m pytest
```

The tests need neither the network nor a browser: the parser runs against the
saved pages in `tests/data`, and the login, order and cancel sequences run
against a stub page (`tests/fake_site.py`) that mimics the postback behaviour
of the site -- including a canteen that takes any number of orders and
cancellations in a row.

```
src/scio_lunch_order/
    browser.py   Playwright session: open, log in, hand over the page HTML
    parser.py    warea markup -> models, dialog and popup texts
    models.py    Menu / Day / MenuOption / FoodItem / Action / OrderResult
    selection.py --day / --item -> the dish to order or cancel
    ordering.py  order / cancel one dish; plan and carry out the whole menu
    choosers.py  how a dish is picked on a day with more of them
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
   hides by setting the css style display to 'none'. The hidden popup stays in
   the page, so before the next order the app waits for the next page to load
   instead of just looking for `infoPanel`.
4. An ordered dish keeps its `Objednat` button and gets a `Zrušit objednávku`
   button next to it.

## Canceling order

1. The ordered dish for the day has the button labeled with "Zrušit objednávku". The cancel button's id is like:
   `repeaterDays_ctl${day index}_repeaterFoodType_ctl${day item index}_repeaterFood_ctl00_btnFood2`
2. Upon clicking the cancel button, the html page displays dialog with the id
   `dialogPanel`. The dialog panel contains the button with id `btnDialogYes`
   in the div with the class `paneldlg__buttons`. The dialog header should be
   `Zrušení objednávky` in the text of the div with the class
   `paneldlg__header` (an order dialog has `Objednání stravy` there). The
   question in `.paneldlg__msg` names the dish and the date:
   `Opravdu si přejete zrušit objednávku <br>bratislavské … dne pondělí 23. listopadu 2026, …?`
3. Clicking `btnDialogYes` reloads the menu with a popup: the div element with
   the id `infoPanel` (`Vaše objednávka byla zrušena`), which a script
   hides by setting the css style display to 'none'. The hidden popup stays in
   the page, so before the next order the app waits for the next page to load
   instead of just looking for `infoPanel`.
4. A cancelled dish loses its `Zrušit objednávku` button and the green
   `Objednáno` mark; its `Objednat` button stays. (Assumed: there is no saved
   page from after a cancellation yet.)

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
