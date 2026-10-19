# Запуск ValutaTrade Hub на Windows

## 1. Подготовка

Установите Git, Python 3.12 (можно через uv) и uv. Откройте PowerShell в папке, куда хотите поместить проект.

Распакуйте ZIP так, чтобы внутри папки проекта сразу находились `pyproject.toml`, `README.md`, `src` и `data`. Например:

`E:\finalproject_kondratev_M26-555`

## 2. Установка окружения

В PowerShell перейдите в корень:

```powershell
cd E:\finalproject_kondratev_M26-555
uv python install 3.12
uv sync
```

`uv sync` разрешит зависимости и создаст `uv.lock`. Этот файл нужно сохранить в Git после установки.

## 3. Проверки

```powershell
uv run ruff check .
uv run python -m unittest discover -s tests -v
uv build
```

Проверьте оба дистрибутива:

```powershell
$files = Get-ChildItem .\dist -File |
    Where-Object {
        $_.Name -like "*.whl" -or
        $_.Name -like "*.tar.gz"
    } |
    Select-Object -ExpandProperty FullName
uvx twine check $files
```

## 4. Запуск CLI

```powershell
uv run valutatrade-hub
```

Пример полного сценария:

```text
register --username alice --password 1234
login --username alice --password 1234
deposit --currency USD --amount 10000
buy --currency BTC --amount 0.05
show-portfolio
sell --currency BTC --amount 0.01
show-portfolio
get-rate --from USD --to BTC
show-rates --top 2
show-rates --currency RUB
help
exit
```

Регистрация создаёт пустой портфель по требованиям задания, поэтому перед покупкой внесите учебный капитал командой `deposit`. Это виртуальное пополнение, оно не затрагивает реальные денежные средства.

## 5. Обновление курсов

Без API-ключа можно обновлять криптокурсы через публичный CoinGecko API:

```text
update-rates --source coingecko
show-rates --top 2
```

Для фиатных курсов зарегистрируйте ключ ExchangeRate-API и задайте его в текущем PowerShell:

```powershell
$env:EXCHANGERATE_API_KEY = "ВАШ_РЕАЛЬНЫЙ_КЛЮЧ"
uv run valutatrade-hub
```

Внутри CLI:

```text
update-rates
show-rates
get-rate --from EUR --to USD
```

Не помещайте настоящий ключ в Python-файлы или Git. Без ключа источник ExchangeRate-API корректно сообщает об ошибке; обновление от CoinGecko продолжает работать.

Для проверки обработки ошибок можно вызвать:

```text
get-rate --from ABC --to USD
sell --currency BTC --amount 100
```

## 6. Сборка и отдельная установка CLI

```powershell
uv build
$wheel = (Get-ChildItem .\dist -Filter "*.whl" | Select-Object -First 1).FullName
uv tool install --force $wheel
valutatrade-hub
```

## 7. Git

Создайте отдельный репозиторий `finalproject_kondratev_M26-555`, затем:

```powershell
git init
git switch -c feature/valutatrade-hub
git add .
git commit -m "Initialize ValutaTrade Hub"
git remote add origin URL_ВАШЕГО_РЕПОЗИТОРИЯ
git push -u origin feature/valutatrade-hub
```

После завершения функциональных частей делайте отдельные осмысленные коммиты. Перед финальным коммитом восстановите начальные данные, если во время демо JSON изменились:

```powershell
git restore data/users.json data/portfolios.json data/rates.json data/exchange_rates.json
```

Так не попадут в репозиторий тестовые пользователи и результаты демонстрационных сделок.

## 8. Демо

Запишите терминальную демонстрацию через asciinema, опубликуйте запись и замените `RECORD_ID` в README. Демо должно включать регистрацию, вход, депозит учебного капитала, buy/sell, show-portfolio, get-rate, update-rates/show-rates и хотя бы одну ошибку валидации.
