; ChatWechat per-user Windows installer.
; The PyInstaller onedir tree is an internal staging input; users receive this setup EXE.
Unicode True
ManifestSupportedOS win10
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
ShowInstDetails show
ShowUninstDetails show

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "0.0.0"
!endif
!ifndef STAGING_ROOT
  !error "STAGING_ROOT is required"
!endif
!ifndef OUTPUT_FILE
  !define OUTPUT_FILE "ChatWechat-Setup.exe"
!endif
!ifndef ICON_FILE
  !define ICON_FILE "${NSISDIR}\Contrib\Graphics\Icons\box-install.ico"
!endif

Name "ChatWechat"
Caption "ChatWechat 安装程序"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\ChatWechat"
InstallDirRegKey HKCU "Software\ChatWechat" "InstallDir"
BrandingText "ChatWechat · 本地微信导出"
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey ProductName "ChatWechat"
VIAddVersionKey ProductVersion "${APP_VERSION}"
VIAddVersionKey FileVersion "${APP_VERSION}"
VIAddVersionKey FileDescription "ChatWechat 本地微信导出安装程序"
VIAddVersionKey CompanyName "ChatWechat"
VIAddVersionKey LegalCopyright "ChatWechat"

!define MUI_ABORTWARNING
!define MUI_ICON "${ICON_FILE}"
!define MUI_UNICON "${ICON_FILE}"
!define MUI_WELCOMEPAGE_TITLE "安装 ChatWechat"
!define MUI_WELCOMEPAGE_TEXT "在当前 Windows 用户下安装 ChatWechat。本程序不会修改微信源数据库。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\ChatWechat.exe"
!define MUI_FINISHPAGE_RUN_TEXT "安装完成后启动 ChatWechat"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
  FindWindow $0 "" "ChatWechat 本地微信导出"
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION|MB_OKCANCEL "ChatWechat 正在运行。请先完成或取消导出并关闭程序，再继续升级。" IDOK continue IDCANCEL abort
    abort:
      Abort
    continue:
  ${EndIf}
FunctionEnd

Function ArchiveLegacyPortable
!ifdef SKIP_LEGACY_MIGRATION
  Return
!endif
  StrCpy $0 "$DESKTOP\免安装便携版\ChatWechat"
  IfFileExists "$0\ChatWechat.exe" 0 done

  ${GetTime} "" "L" $1 $2 $3 $4 $5 $6 $7
  StrCpy $8 "$DESKTOP\免安装便携版\ChatWechat-portable-backup-$3$2$1-$4$5$6"
  StrCpy $9 1
  next_name:
    IfFileExists "$8\*.*" 0 rename
    StrCpy $8 "$DESKTOP\免安装便携版\ChatWechat-portable-backup-$3$2$1-$4$5$6-$9"
    IntOp $9 $9 + 1
    Goto next_name
  rename:
    Rename "$0" "$8"
    IfErrors migration_failed
    DetailPrint "旧便携版已归档：$8"
    Goto done
  migration_failed:
    DetailPrint "旧便携版未能自动归档，将保留原目录。"
  done:
FunctionEnd

Section "ChatWechat" SecMain
  ; The install directory is separate from %LOCALAPPDATA%\ChatWechat user data.
  RMDir /r "$INSTDIR"
  SetOutPath "$INSTDIR"
  File /r "${STAGING_ROOT}\*.*"

  WriteRegStr HKCU "Software\ChatWechat" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatWechat" "DisplayName" "ChatWechat"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatWechat" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatWechat" "Publisher" "ChatWechat"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatWechat" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatWechat" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatWechat" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatWechat" "NoRepair" 1

  WriteUninstaller "$INSTDIR\Uninstall.exe"
!ifndef SKIP_SHORTCUTS
  CreateDirectory "$SMPROGRAMS\ChatWechat"
  CreateShortcut "$SMPROGRAMS\ChatWechat\ChatWechat.lnk" "$INSTDIR\ChatWechat.exe"
  CreateShortcut "$SMPROGRAMS\ChatWechat\卸载 ChatWechat.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\ChatWechat.lnk" "$INSTDIR\ChatWechat.exe"
!endif
SectionEnd

Section "-MigrateLegacyPortable"
  Call ArchiveLegacyPortable
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\ChatWechat.lnk"
  Delete "$SMPROGRAMS\ChatWechat\ChatWechat.lnk"
  Delete "$SMPROGRAMS\ChatWechat\卸载 ChatWechat.lnk"
  RMDir "$SMPROGRAMS\ChatWechat"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChatWechat"
  DeleteRegKey HKCU "Software\ChatWechat"
  RMDir /r "$INSTDIR"
SectionEnd

