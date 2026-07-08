#!/usr/bin/env python3
import os
import sys
import ast
import shutil
import argparse
import subprocess
import tempfile
from datetime import datetime

# Flexible TOML loading to support structural merging
# Using tomlkit is highly recommended for preserving comments, fallback to tomllib/tomli
TOMLKIT_AVAILABLE = False
try:
	import tomlkit
	TOMLKIT_AVAILABLE = True
except ImportError:
	try:
		import tomllib  # Python 3.11+
	except ImportError:
		try:
			import tomli as tomllib
		except ImportError:
			print("Error: The 'tomlkit', 'tomllib' or 'tomli' module is required to run this script.")
			print("Please install it using: pip install tomli tomlkit")
			input("\nPress Enter to exit...")
			sys.exit(1)

def deepMergeDicts(dictProj, dictTpl):
	"""Recursively merges dictTpl into dictProj. Supports both dict and tomlkit container types."""
	for key, value in dictTpl.items():
		if key in dictProj:
			if hasattr(dictProj[key], 'items') and hasattr(value, 'items'):
				deepMergeDicts(dictProj[key], value)
			elif isinstance(dictProj[key], list) and isinstance(value, list):
				for item in value:
					if item not in dictProj[key]:
						dictProj[key].append(item)
			else:
				pass
		else:
			dictProj[key] = value
	return dictProj

def extractBuildvarsMetadata(filePath):
	"""Extracts metadata from an old buildVars.py file safely using modern AST APIs."""
	if not os.path.exists(filePath):
		return {}, {}

	with open(filePath, "r", encoding="utf-8") as f:
		try:
			tree = ast.parse(f.read())
		except SyntaxError as e:
			print(f"[-] Syntax error while reading {filePath}: {e}")
			return {}, {}

	metadata = {}
	globalVars = {}
	topLevelVars = {
		'pythonSources', 'excludedFiles', 'baseLanguage', 'markdownExtensions',
		'brailleTables', 'symbolDictionaries', 'speechDictionaries'
	}

	for node in ast.walk(tree):
		if isinstance(node, ast.Assign) and len(node.targets) == 1:
			target = node.targets[0]
			if not isinstance(target, ast.Name):
				continue
			varName = target.id

			if varName == "addon_info":
				if isinstance(node.value, ast.Dict):
					for keyNode, valNode in zip(node.value.keys, node.value.values):
						key = getattr(keyNode, 'value', None)
						if isinstance(valNode, ast.Call) and getattr(valNode.func, 'id', None) == '_':
							valNode = valNode.args[0]
						val = getattr(valNode, 'value', None)
						if key is not None:
							metadata[key] = val
				elif isinstance(node.value, ast.Call) and getattr(node.value.func, 'id', None) == "AddonInfo":
					for keyword in node.value.keywords:
						key = keyword.arg
						valNode = keyword.value
						if isinstance(valNode, ast.Call) and getattr(valNode.func, 'id', None) == '_':
							valNode = valNode.args[0]
						val = getattr(valNode, 'value', None)
						metadata[key] = val
			elif varName in topLevelVars:
				globalVars[varName] = ast.unparse(node.value)
		elif isinstance(node, ast.AnnAssign):
			if isinstance(node.target, ast.Name) and node.target.id in topLevelVars:
				globalVars[node.target.id] = ast.unparse(node.value)

	return metadata, globalVars

def mergePyprojectToml(projPath, tplPath, dryRun=False):
	"""Merges template pyproject.toml configuration into the developer's file."""
	if not os.path.exists(tplPath):
		return "skipped (no template)"
	
	if not os.path.exists(projPath):
		if not dryRun:
			shutil.copy2(tplPath, projPath)
		return "created from template"

	try:
		if TOMLKIT_AVAILABLE:
			with open(projPath, "r", encoding="utf-8") as f:
				projData = tomlkit.parse(f.read())
			with open(tplPath, "r", encoding="utf-8") as f:
				tplData = tomlkit.parse(f.read())
			
			mergedData = deepMergeDicts(projData, tplData)
			if not dryRun:
				with open(projPath, "w", encoding="utf-8") as f:
					f.write(tomlkit.dumps(mergedData))
			return "merged intelligently (tomlkit)"
		else:
			return "preserved (install 'tomlkit' for automated smart merging)"
	except Exception as e:
		return f"failed to merge ({str(e)})"

def mergeBuildvarsFile(projPath, tplPath, metadata, globalVars, dryRun=False):
	"""Merges template buildVars.py using precise AST range tracking to prevent multiline leaks."""
	if not os.path.exists(tplPath):
		return "failed (no template found)"
	
	with open(tplPath, "r", encoding="utf-8") as f:
		tplContent = f.read()
	
	try:
		tree = ast.parse(tplContent)
	except SyntaxError as e:
		return f"failed (template syntax error: {e})"

	tplLines = tplContent.splitlines(keepends=True)
	replacements = {}

	for node in ast.walk(tree):
		if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == "AddonInfo":
			for kw in node.keywords:
				if kw.arg in metadata:
					key = kw.arg
					val = metadata[key]
					if val is None:
						formattedVal = "None"
					elif isinstance(val, str):
						formattedVal = f'_("""{val}""")' if key in ['addon_summary', 'addon_description', 'addon_changelog'] else f'"{val}"'
					else:
						formattedVal = str(val)
					
					indent = tplLines[kw.lineno - 1][:len(tplLines[kw.lineno - 1]) - len(tplLines[kw.lineno - 1].lstrip())]
					replacements[(kw.lineno - 1, kw.end_lineno)] = f"{indent}{key}={formattedVal},\n"
		
		elif isinstance(node, ast.Assign) and len(node.targets) == 1:
			target = node.targets[0]
			if isinstance(target, ast.Name) and target.id in globalVars:
				key = target.id
				valExpression = globalVars[key]
				indent = tplLines[node.lineno - 1][:len(tplLines[node.lineno - 1]) - len(tplLines[node.lineno - 1].lstrip())]
				
				# Dynamic fix: Prepend import os inline if the assignment expression uses the os module
				prefix = f"{indent}import os\n" if "os." in valExpression else ""
				replacements[(node.lineno - 1, node.end_lineno)] = f"{prefix}{indent}{key} = {valExpression}\n"
				
		elif isinstance(node, ast.AnnAssign):
			if isinstance(node.target, ast.Name) and node.target.id in globalVars:
				key = node.target.id
				valExpression = globalVars[key]
				indent = tplLines[node.lineno - 1][:len(tplLines[node.lineno - 1]) - len(tplLines[node.lineno - 1].lstrip())]
				typeStr = ast.unparse(node.annotation)
				
				# Dynamic fix: Prepend import os inline if the annotation assignment expression uses the os module
				prefix = f"{indent}import os\n" if "os." in valExpression else ""
				replacements[(node.lineno - 1, node.end_lineno)] = f"{prefix}{indent}{key}: {typeStr} = {valExpression}\n"

	sortedRanges = sorted(replacements.keys(), key=lambda x: x[0], reverse=True)
	for start, end in sortedRanges:
		tplLines[start:end] = [replacements[(start, end)]]

	if not dryRun:
		with open(projPath, "w", encoding="utf-8") as f:
			f.writelines(tplLines)
	return "merged & structured (AST verified)"

def main():
	parser = argparse.ArgumentParser(description="Non-destructive industrial migration tool for NVDA Add-ons.")
	parser.add_argument("addonDir", nargs="?", default=None, help="Path to the root directory of the add-on to update (defaults to current directory).")
	parser.add_argument("--dry-run", dest="dryRun", action="store_true", help="Simulate execution without modifying any files.")
	parser.add_argument("--skip-backup", dest="skipBackup", action="store_true", help="Disable safety automatic project backup.")
	args = parser.parse_args()

	addonDirInput = args.addonDir if args.addonDir else os.getcwd()
	addonDir = os.path.abspath(addonDirInput)

	print("=== NVDA ADD-ON MIGRATION TOOL ===")
	print(f"[*] Target Directory: {addonDir}")

	oldBuildvars = os.path.join(addonDir, "buildVars.py")
	oldPyproject = os.path.join(addonDir, "pyproject.toml")
	
	if not os.path.exists(oldBuildvars):
		print(f"[-] Error: '{addonDir}' does not appear to be a valid NVDA Add-on (missing buildVars.py).")
		input("\nPress Enter to exit...")
		sys.exit(1)

	print("[*] Phase 1: Analyzing existing project structure and metadata...")
	bvMeta, bvGlobals = extractBuildvarsMetadata(oldBuildvars)
	addonName = bvMeta.get("addon_name", os.path.basename(addonDir))
	print(f"[+] Target Add-on Identified: {addonName}")

	if args.dryRun:
		print("[!] RUNNING IN SIMULATION MODE (--dry-run). No files will be modified.")

	if not args.skipBackup and not args.dryRun:
		backupDir = f"{addonDir}_bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
		print(f"[*] Phase 2: Creating safety automatic backup in: {os.path.basename(backupDir)}...")
		try:
			shutil.copytree(addonDir, backupDir, ignore=shutil.ignore_patterns('.git', '__pycache__', '.venv', '*_bak_*'))
			print("[+] Backup created successfully.")
		except Exception as e:
			print(f"[-] Critical: Backup failed ({e}). Aborting migration.")
			input("\nPress Enter to exit...")
			sys.exit(1)
	else:
		print("[*] Phase 2: Safety backup skipped.")

	print("[*] Phase 3: Provisioning latest official NVDA AddonTemplate via Git...")
	
	with tempfile.TemporaryDirectory() as tempDir:
		print(f"[*] Cloning template into temporary workspace...")
		templateUrl = "https://github.com/nvaccess/AddonTemplate.git"
		
		try:
			subprocess.run(
				["git", "clone", "--depth", "1", templateUrl, tempDir],
				check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
			)
			print("[+] Template cloned successfully.")
		except (subprocess.CalledProcessError, FileNotFoundError) as e:
			print(f"[-] Error: Failed to execute git clone. Make sure Git is installed and available in your PATH.")
			if hasattr(e, 'stderr') and e.stderr:
				print(f"Details: {e.stderr.decode('utf-8', errors='ignore')}")
			input("\nPress Enter to exit...")
			sys.exit(1)

		print("[*] Synchronizing template machinery files...")
		protectedElements = {"readme.md", "changelog.md", "addon", ".git", "__pycache__", ".venv", "docs", ".ruff_cache", "migrate.py"}
		syncReport = []

		for item in os.listdir(tempDir):
			if item.lower() in protectedElements:
				syncReport.append(f"{item} .................... skipped (protected scope)")
				continue
			
			if item in ["buildVars.py", "pyproject.toml"]:
				continue

			srcItem = os.path.join(tempDir, item)
			dstItem = os.path.join(addonDir, item)
			
			try:
				if os.path.isdir(srcItem):
					if not args.dryRun:
						os.makedirs(dstItem, exist_ok=True)
						shutil.copytree(srcItem, dstItem, dirs_exist_ok=True)
					syncReport.append(f"{item}/ ................... merged safely")
				else:
					if not args.dryRun:
						shutil.copy2(srcItem, dstItem)
					syncReport.append(f"{item} .................... synchronized")
			except Exception as e:
				syncReport.append(f"{item} .................... failed ({str(e)})")

		print("[*] Phase 4: Processing structural configuration merges...")
		templateBuildvars = os.path.join(tempDir, "buildVars.py")
		templatePyproject = os.path.join(tempDir, "pyproject.toml")

		bvStatus = mergeBuildvarsFile(oldBuildvars, templateBuildvars, bvMeta, bvGlobals, args.dryRun)
		ppStatus = mergePyprojectToml(oldPyproject, templatePyproject, args.dryRun)

		print("\n" + "=" * 50)
		print("MIGRATION REPORT")
		print("=" * 50)
		print(f"Add-on ....................... {addonName}")
		print("\nTemplate synchronization:")
		for entry in syncReport:
			print(f"  - {entry}")
		print(f"\nConfiguration files:\n  buildVars.py ............... {bvStatus}\n  pyproject.toml ............. {ppStatus}")
		
		if not args.dryRun:
			print("\n[+] Project successfully migrated. Temporary workspace destroyed.")
		else:
			print("\n[+] Simulation finished. Workspace cleared.")

	input("\nPress Enter to exit...")

if __name__ == "__main__":
	main()
    