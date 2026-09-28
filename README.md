# Проект Линия — списки доменов

Один список `data/line` автоматически собирается в два формата:

| Назначение | Постоянная ссылка |
| --- | --- |
| Xray / 3x-ui, категория `line` | [geosite_line.dat](https://github.com/nozloy/line_geosite/releases/latest/download/geosite_line.dat) |
| sing-box / OpenWrt, бинарный rule-set | [geosite_line.srs](https://github.com/nozloy/line_geosite/releases/latest/download/geosite_line.srs) |
| Контрольная сумма DAT | [geosite_line.dat.sha256sum](https://github.com/nozloy/line_geosite/releases/latest/download/geosite_line.dat.sha256sum) |
| Контрольная сумма SRS | [geosite_line.srs.sha256sum](https://github.com/nozloy/line_geosite/releases/latest/download/geosite_line.srs.sha256sum) |

Оба файла охватывают каждый указанный домен и все его поддомены. Например,
`asos.com` и `www.asos.com` входят в список, а `notasos.com` — нет.
В список входят только адреса из `data/line`; внешние каталоги доменов не добавляются.
Связанные CDN, платёжные и другие сторонние домены автоматически не включаются.

## Изменение списка

Редактируйте `data/line`: один адрес в строке, например `domain:asos.com`.
Используйте строчные ASCII-имена без протокола, пути, порта, `*` и завершающей точки.
Для IDN используйте punycode. Пустые строки и комментарии после `#` разрешены.
Дубликаты и поддомены уже внесённого родительского домена нужно удалить.

После push в `main` GitHub Actions проверяет список, собирает оба файла и публикует
новый релиз. Ссылки выше остаются прежними. Pull request запускает только проверки;
ручной запуск доступен в Actions → Build and publish domain lists → Run workflow.

Релиз сначала создаётся как черновик. Он становится Latest после загрузки и
побайтовой проверки всех четырёх файлов. Если скачивание черновика для проверки
завершилось ошибкой GitHub, выполняются до четырёх попыток с паузами 2, 4 и 8 секунд.
Незавершённые скачивания перезаписываются и проверяются заново.
Ошибка сборки или загрузки сохраняет
предыдущий опубликованный релиз. Устаревший запуск не назначается Latest.
Сбой загрузки или новый push во время загрузки может оставить диагностический черновик.
Предыдущие опубликованные релизы сохраняются для отката или фиксации версии.

## Xray / 3x-ui 3.8.5

1. Первично загрузите `geosite_line.dat` в фактический каталог ресурсов Xray.
   В обычной установке 3x-ui это каталог с бинарником Xray, задаваемый `XUI_BIN_FOLDER`.
   Для Docker используйте постоянный том этого каталога.
2. В настройках Geodata профиля добавьте URL DAT из таблицы и имя файла
   `geosite_line.dat`. Сохраните существующие источники и выберите нужное расписание.
3. В поле Domain нужного правила маршрутизации укажите:

   ```text
   ext:geosite_line.dat:line
   ```

4. Привяжите правило к существующему выходу и расположите его до более общего
   правила, которое иначе перехватит эти домены. Сохраните и примените профиль.

Пример **элемента** массива `geodata.assets` для добавления в существующий профиль:

```json
{
  "url": "https://github.com/nozloy/line_geosite/releases/latest/download/geosite_line.dat",
  "file": "geosite_line.dat"
}
```

[Механизм Geodata Xray](https://xtls.github.io/en/config/geodata.html) обновляет
уже существующие файлы: одного добавления URL недостаточно для первичной установки.
При обновлении через расписание нужен совместимый Xray-core с поддержкой `geodata`.

Пример первичной загрузки на Linux. Сначала замените `asset_dir` на реальный
каталог ресурсов вашей установки; команды выполняются с правами записи в него.

```bash
(
  set -eu
  asset_dir='/usr/local/x-ui/bin'
  work_dir="$(mktemp -d)"
  trap 'rm -rf -- "$work_dir"' EXIT
  cd "$work_dir"
  base='https://github.com/nozloy/line_geosite/releases/latest/download'
  curl --fail --location --retry 3 --output geosite_line.dat "$base/geosite_line.dat"
  curl --fail --location --retry 3 --output geosite_line.dat.sha256sum "$base/geosite_line.dat.sha256sum"
  sha256sum --check geosite_line.dat.sha256sum
  install -m 0644 geosite_line.dat "$asset_dir/geosite_line.dat"
)
```

Если релиз сменился между двумя скачиваниями и сумма не совпала, повторите загрузку.
Добавляйте правило `ext:` только после успешного размещения файла.

## OpenWrt / sing-box

`geosite_line.srs` — бинарный rule-set **версии 2**, совместимый с **sing-box 1.10+**.
Архитектура процессора роутера не влияет на формат файла. Для приложения на OpenWrt,
поддерживающего sing-box rule-set, выберите удалённый источник, формат **binary / SRS**
и URL SRS из таблицы. Имя / tag списка: `line`.

Пример элемента `route.rule_set` в конфигурации sing-box:

```json
{
  "type": "remote",
  "tag": "line",
  "format": "binary",
  "url": "https://github.com/nozloy/line_geosite/releases/latest/download/geosite_line.srs",
  "update_interval": "1d"
}
```

Затем используйте `"rule_set": ["line"]` в нужном правиле маршрутизации или DNS.
Само подключение источника ещё не выбирает выход для этих доменов.
В LuCI название раздела зависит от установленного приложения.

Версия файла закреплена независимо от версии сборщика: новые версии sing-box
не должны автоматически повышать требования к роутеру.
Документация: [rule-set](https://sing-box.sagernet.org/configuration/rule-set/),
[версии SRS](https://sing-box.sagernet.org/configuration/rule-set/source-format/).

## Локальная сборка и проверки

Требуются Go **1.25.12**, Python **3.11+**, Bash и доступ к GitHub/Go Modules.
Поддерживаемые машины сборки: Linux x86_64 и macOS arm64. Файлы для использования
на сервере или роутере не зависят от архитектуры машины сборки.

```bash
python3 scripts/build.py
python3 scripts/verify.py
```

Сборка создаёт четыре файла в `dist/`. Проверки включают чтение DAT штатным
`datdump`, декомпиляцию SRS с проверкой полного списка и версии, проверку совпадений
для доменов/поддоменов и отказа для похожих посторонних имён, повторяемость
обоих форматов, отказ для пустого/некорректного ввода и загрузку категории
реальным Xray через `run -test` без запуска сервера. Публикация отдельно проверяется
с подменой GitHub CLI, без сетевых записей.

Дополнительные параметры: `python3 scripts/build.py --source data/line --output dist`.
Версии сборщиков и контрольные суммы официальных CLI-архивов закреплены в
`toolchains.json`; версия Go — в `.go-version`. CLI скачиваются в `.cache/`
с проверкой SHA-256. Сборщик DAT: [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community).
`dist/` и `.cache/` не коммитятся. Дополнительные GitHub secrets не нужны:
публикация использует штатный `GITHUB_TOKEN` только в отдельном job с `contents: write`.
