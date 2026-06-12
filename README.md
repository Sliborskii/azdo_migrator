# Azure DevOps Migration Tool (azdo_migrator)

Утилита для полной и аккуратной миграции проектов между организациями Azure DevOps. 

Отличительной особенностью этого инструмента является его способность не просто "скопировать" данные, но и **ретроспективно исправить** исторические артефакты:
- Починить "фантомных" пользователей (у которых сменился email-домен).
- Скачать и перезалить внутренние картинки из описаний задач.
- Починить битые ссылки на задачи (в том числе упоминания `#123`).
- Заменить абсолютные ссылки на Wiki-страницы на работающие динамические линки.
- Сделать массовую замену перекрестных ссылок внутри Markdown-файлов самой Wiki.

## 1. Подготовка (Prerequisites)

1. **Python 3.9+**
2. Склонируйте репозиторий и установите зависимости:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Создайте `config.json` на основе `config.example.json`. Вам потребуются:
   - **Source PAT** (Personal Access Token) со старого Azure DevOps.
   - **Target PAT** с нового Azure DevOps.
   > Токены должны иметь права **Read & Write** на Work Items, Identity и Graph.

## 2. Шаг 1: Базовая миграция

На этом этапе мы переносим структуру и сами задачи.

1. **Синхронизация спринтов и Area Paths:**
   ```bash
   python -m azdo_migrator.cli --config config.json --sync-sprints
   ```

2. **Миграция всех Work Items:**
   ```bash
   python -m azdo_migrator.cli --config config.json --sync-workitems
   ```
   > [!WARNING]
   > При выполнении этой команды создастся файл `migration_state.json`, который содержит "карту" старых ID и новых ID задач. **Не удаляйте его!** Он жизненно необходим для всех последующих исправлений.

## 3. Шаг 2: Лечение "детских болезней" (Post-Migration Fixes)

В момент создания задач система еще не знает всех связей (так как некоторые задачи еще не созданы). Кроме того, у сотрудников могли измениться почтовые домены.

### А) Исправление исполнителей (Users)
1. **Генерация карты пользователей:**
   ```bash
   python -m azdo_migrator.cli --config config.json --generate-users
   ```
   Это выгрузит списки людей из старого и нового Graph API и создаст `user_mapping.json`.
2. **Ручная выверка:** Откройте `user_mapping.json`. Те пользователи, для которых система не нашла совпадений в новом ADO, будут отмечены как `null`. Вручную впишите туда валидный email нового сотрудника (или свой email), на которого вы хотите перевесить эти задачи.
3. **Применение исполнителей:**
   ```bash
   python -m azdo_migrator.cli --config config.json --fix-users
   ```

### Б) Исправление ссылок, картинок и упоминаний
Выполните эти три команды по очереди, чтобы "причесать" текст в описаниях и комментариях:
```bash
# Исправляет упоминания людей (@Name)
python -m azdo_migrator.cli --config config.json --fix-mentions

# Скачивает картинки из старого ADO и заливает в новый
python -m azdo_migrator.cli --config config.json --fix-images

# Чинит перекрестные ссылки на задачи (в т.ч. #123) и ссылки на Wiki
python -m azdo_migrator.cli --config config.json --fix-links
```

## 4. Шаг 3: Миграция самой Wiki

Так как Wiki в Azure DevOps — это обычный Git-репозиторий, мы переносим его через Git, но предварительно "чиним" Markdown-файлы.

1. Склонируйте старую Wiki на свой компьютер:
   ```bash
   git clone https://dev.azure.com/OLD_ORG/OLD_PROJ/_git/OLD_PROJ.wiki
   ```
2. Натравите на эту папку наш встроенный скрипт:
   ```bash
   python -m azdo_migrator.cli --config config.json --fix-wiki-repo /путь/к/склонированной/папке
   ```
   > [!NOTE]
   > Скрипт использует ваш `migration_state.json` и API старого ADO, чтобы найти в Markdown-файлах все упоминания `#123` и абсолютные URL-ссылки `_wiki/wikis/.../Settings`, и заменяет их на новые валидные ссылки. Таким образом, **кросс-линки между Wiki и задачами работают в обе стороны!**
3. Запушьте результат в новую Wiki:
   ```bash
   cd /путь/к/склонированной/папке
   git remote add target https://dev.azure.com/NEW_ORG/NEW_PROJ/_git/NEW_PROJ.wiki
   git push target main
   ```

## Быстрый запуск

Если вы уверены, что `user_mapping.json` генерируется идеально, вы можете запустить весь пайплайн (кроме Wiki) одной командой:
```bash
python -m azdo_migrator.cli --config config.json --all
```
Но рекомендуется проходить шаги последовательно для контроля качества миграции.
