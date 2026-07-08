# NVDA Add-on Migrator

An automated, AST-based industrial migration tool designed to non-destructively update NVDA add-ons to the latest official `nvaccess/AddonTemplate` framework.

---

## How to Use This Tool (Step-by-Step Migration Guide)

### Method A: Using the Standalone Executable (Recommended for Add-on Authors)

If you have downloaded or generated the standalone `nvda-addon-migrator.exe` file, follow these simple steps to upgrade your add-on:

1.	**Deploy the Executable:** Copy `nvda-addon-migrator.exe` and paste it directly inside the root directory of your cloned NVDA add-on repository (place it at the exact same level as your add-on's `buildVars.py` and `.git` folder).
2.	**Run the Automation:** Double-click `nvda-addon-migrator.exe`. Alternatively, open a command prompt (cmd) or PowerShell window inside that folder and execute:
	```cmd
	.\nvda-addon-migrator.exe
	```
3.	**Verify and Test:** Once the script completes, a migration summary will display in the console. The tool will have automatically updated your configuration files using structural AST injection. You can now immediately run SCons to test your upgraded build machinery:
	```cmd
	scons
	```

### Method B: Running the Python Source Code Directly via `uv`

If you are running the source code directly from this repository using `uv`, you do not need to compile anything. Follow this workflow:

1.	**Open a Terminal:** Navigate to your local copy of the `nvda-addon-migrator` tool.
2.	**Execute the Migration Command:** Call the script using `uv run` while providing the absolute or relative path to your outdated add-on folder as an argument:
	```
	# Syntax: uv run src/nvda_migrator/migrate.py "C:\path\to\your\outdated-addon-repo"
	uv run src/nvda_migrator/migrate.py "../my-nvda-addon"
	```
	*Note: If you copy the `migrate.py` script directly into your add-on folder, you can just run `uv run migrate.py` with zero arguments, and it will automatically target the current directory.*
3.	**Optional CLI Arguments:**
	*	`--dry-run` : Simulates the entire process and shows a report without modifying any files on disk.
	*	`--skip-backup` : Disables the safety feature that automatically creates a timestamped zip/directory backup of your project before updating.

---

## How the Template Update Works Under the Hood

When executed, the tool safely automates the entire infrastructure upgrade process:

1.	**Cloning the Latest Framework:** The tool clones the fresh, up-to-date master branch of `https://github.com/nvaccess/AddonTemplate.git` into an isolated temporary workspace.
2.	**Replacing Build Machinery:** It copies all modern build systems, helper scripts, GitHub Actions workflows, SCons tools (`site_scons/`), and tool configurations (like `.gitignore` or linting rules) from the fresh template into your repository.
3.	**Surgically Migrating Metadata:**
	*	It reads your legacy `buildVars.py` and extracts your add-on identity using static AST analysis. The parser is retro-compatible and intelligently handles legacy formats where `addon_info` was defined as a standard Python **dictionary object (`dict`)**, as well as newer formats where it is instantiated as an **`AddonInfo` class object**.
	*	It safely injects these extracted values into the brand-new `buildVars.py` structural format provided by the template.
	*	It merges your local tool setups inside `pyproject.toml` with the template's new defaults (preserving custom hooks or dependency lists).
4.	**Protecting Custom Source Files:** The migration process strictly isolates and protects your actual add-on business logic (`addon/`), your translation catalogs (`locale/`), your documentation (`docs/`, `readme.md`, `changelog.md`), and your local Git history (`.git/`).

---

## Key Features

*	**Zero-Configuration:** When executed without any arguments, it automatically targets the current working directory.
*	**Ephemeral Remote Syncing:** Automatically creates, manages, and completely destroys the secure remote template Git workspace upon completion.
*	**AST-Based Merging:** Uses Python's Abstract Syntax Tree to map code node coordinates, preventing `SyntaxError` issues and leaked quotes common with raw text replacement tools.
*	**Smart Dictionary Merging:** Merges configurations (like `pyproject.toml` or Ruff rules) instead of blindly overwriting them.

---

## Development & Environment Setup

This project leverages `uv` for lightning-fast environment provisioning and dependency tracking.

### 1. Requirements
*	Python 3.13 or 3.14
*	Git available in your system's `PATH`
*	`uv` installed globally on your system (Install via: `pip install uv` or official installers)

### 2. Setup
To bootstrap your local workspace and synchronize all core, linting, and compilation dependencies, simply run:

```
uv sync --all-extras

### 3. Pre-commit Hooks Setup
To activate automated checks before each commit, run:

```
uv run pre-commit install
```

###4. Code Quality (Linting & Formatting)
To manually check the codebase using Ruff and Pyright:

```
uv run ruff check .
uv run pyright
```
###5. Compiling to a Standalone Executable (.exe)
To package the script into a standalone .exe file for distribution using the repository's PyInstaller specification, run the following command:

```
uv run pyinstaller nvda-addon-migrator.spec
```

The compiled executable and its build artifacts will be generated, and the final binary will be located inside the dist/ directory.
