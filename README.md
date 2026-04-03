# Antifraud2GIS

Searching for fake (suspicious) reviews in 2gis.

This project is absolutely unofficial, not related to 2GIS.ru.

## Installation
~~~
pipx install git+https://github.com/yaroslaff/antifraud2gis
~~~

## Basic operations

- `af2gis` - main program for most user operations
- `af2dev` - program for developers 
- `af2web` - webserver (probably you do not need it)
- `af2worker` - background worker (probably you do not need it too)

If you want just to run fraud detection on companies by 2GIS object-id, you need to use only `af2gis`.


### Basic commands
~~~

# make fraud report for company
af2dev reports fraud 141265769338187

# or short form (same effect)
af2dev rf 141265769338187

# same by allias
af2dev rf nskzoo

# list all aliases:
af2gis aliases
~~~

### Other commands

#### Companies

~~~
# search local database
af2dev cl 'ваши окна'
af2dev cl 'ваши окна' -r 1

# complex search in database, including counting nreviews
af2dev cl 'окна' -r 1  --nr --expr 'rating_2gis is not None and rating_2gis>4.7 and nreviews>10' -f json | jq

# company fetch from 2gis
af2dev cf 141265769826185 -f


~~~

#### Metrics
~~~
# list
af2dev ml nskzoo
~~~

#### Percentiles
~~~
# list for region 1 (nsk)
af2dev pl -r 1

# list for metric
af2dev pl -r 1 -m neigh:ratio
~~~



Next call to fraud detection will show old result unless `--overwrite` option given.

### Explore town (crawl, index new companies)
You need to have at least few users already crawled (from previous fraud detections).
Explore will submit jobs to redis queue, and you need to have af2worker running to process queue.

~~~
af2dev explore -t Новосибирск
~~~

`-t` will limit only to specific town.

"Explore" may look slow or even hangs, but you may check summary or queue status in other tab every 3-5 minutes to see progress. (It really hangs only if af2worker is not running)


### local db summary
~~~
$ af2gis summary 
2025-05-04 16:15:35 SUMMARY Companies: total=3, nerr=0 ncalc=3 nncalc=0
2025-05-04 16:15:35 SUMMARY LMDB prefixes: {'object': 12053, 'user': 900}
~~~

Companies (on first line) are companies which are downloaded, objects (on second line) - companies which are known (but not downloaded).

### Queue status
Use `af2dev queue` (or just `q`).
~~~
$ af2dev q
Queue report
Worker status: started...
Dramatiq queue: 0
Tasks (0): [] 
Trusted (5/20):
  141265771582384 СберБанк, Банки (3.6) None
  70000001025692296 Нск Шашлык, Быстрое питание (4.8) None
  70000001026944015 Дивногорский, управляющая компания (3) None
  70000001023639031 Сибкарт моторспорт, картинг-центр (4.7) None
  141265771632879 Подорожник, доступная кофейня (2.2) None
Untrusted (5/11)
  70000001091636066 Культура, рюмочная (5) ['risk_users 84% (222 / 262)']
  70000001091636066 Культура, рюмочная (5) ['risk_users 84% (222 / 262)']
  70000001083008185 Рыдзинский, рюмочная-караоке (4.9) ['risk_users 41% (179 / 432)']
  5348552838629866 Юсуповский Дворец на Мойке, музей (4.9) ['sametitle_rel 20% (5 of 1)']
  5348552838629866 Юсуповский Дворец на Мойке, музей (4.9) ['sametitle_rel 20% (5 of 1)']
~~~

## Search by substring
SQLite database has data about all companies after fraud-detect. Company itself and top of company's *neighbour* (related) companies are added to database.

~~~
$ af2gis search арн -t Новосибирск
{'oid': '70000001075178717', 'title': 'Пекарня, Пекарни', 'address': 'Новосибирск, Урожайная, 8', 'town': 'Новосибирск', 'searchstr': 'новосибирск пекарня, пекарни', 'rating_2gis': 4.7, 'trusted': 1, 'nreviews': 31, 'detections': ''}
{'oid': '70000001041433989', 'title': 'Пекарня, Пекарни', 'address': 'Новосибирск, Чигорина, 3', 'town': 'Новосибирск', 'searchstr': 'новосибирск пекарня, пекарни', 'rating_2gis': 4.6, 'trusted': 1, 'nreviews': 52, 'detections': ''}
~~~

LMDB database has data about all ever seen companies (even if company was once seen in one user reviews)
~~~
mir ~/repo/antifraud2gis $ af2dev lmdb дог
object:70000001007492207
{
  "name": "Хот-дог райский, киоск фастфудной продукции",
  "address": "Новосибирск, проспект Дзержинского, 23"
}
object:70000001017423547
{
  "name": "Хот-дог Мастер, фуд-киоск",
  "address": "Новосибирск, проспект Карла Маркса, 4а"
}
...
~~~

## Adjust settings

Settings variables can be overriden in environment or .env file.

You can always see accurate current defaults in [settings.py](src/antifraud2gis/settings.py).

### Common settings

If company has less then `MIN_REVIEWS` (20) it will be considered trusted without any other checks.

Only reviews with age under `MAX_REVIEW_AGE` (730 days) are processed. (Older reviews are counted as `discarded`)

`SKIP_OIDS` and `DEBUG_UIDS` are space-separated list of UID/OIDs to ignore/debug. (only for debugging purposes, not for users).

### Relation-specific

Definition: 
Relation between companies A and B is *high* if it has many hits (>= `RISK_HIT`).
Relation is *happy* if avg rating for both A/B companies in relation are >= `RISK_HIGHRATE`

For *sametitle* check: check applied only if company has more then `SAMETITLE_REL` (3) 'happy' relations, and total different titles in relations ( / total happy relations) are under `SAMETITLE_RATIO` (percents). 

For *happy long relations* check: check applied if number of towns are >= `HAPPY_LONG_REL_MIN_TOWNS` (3) and *happy ratio* (ratio of happy hight relations to all high relations) is over `HAPPY_LONG_REL` (50%). *happy_long_rel* calculated as unique_towns / happy_high_relations. (If each happy high relation belongs to different town, *happy_long_rel* will be 1). Detection will be if this value is >= then `HAPPY_LONG_REL` (10).

Risk users are users in such risk (high and happy) relations. If ratio of risk users are over `RISK_USER` (30), detection happens.

### Empty users

User is *empty* if it has no visible reviews for other companies (user is external or has private profile) or user have just one review for this company only.

Test applied only if company has more then `APPLY_EMPTY_USER` reviews from empty users and from non-empty users. Fraud detected if company has more then `EMPTY_USER` (75%) empty users and avg rating about empty users are more then `RATING_DIFF` (1.2) higher then rating among non-empty users.

### Reviews per user
Simple/cheap bots often have very few reviews. Check is applied only if processed (= from not empty users) more then `APPLY_MEDIAN_RPU` (20) reviews. Detection happens if median number of reviews per user is lower then `MEDIAN_RPU` (5) and rating amount low-RPU users and high-RPU users are over `RATING_DIFF`.

### User age
*User age* is age in days between a first review of user and a current review. (so, each user has at least one review with user age = 0). Check is applied only if processed more then `APPLY_MEDIAN_UA` (20) reviews, if median user age is under `MEDIAN_USER_AGE` (30) days, there is at least `MEDIAN_USER_AGE_NUSERS` (10) *young* users and rating among young users are more then `RATING_DIFF` if compare with *old* users.

### Displaying results
Console utility shows all high relations between companies, `SHOW_HIT` used to display relations with lower hit count. Can be overriden with `-s N` option. 

`RISK_MEDIAN` will highlight median number of user reviews if it's under this value. (Bots often has low number of reviews).

Neither `SHOW_HIT` nor `RISK_MEDIAN` do not affect detections, it's used only for displaying information.



