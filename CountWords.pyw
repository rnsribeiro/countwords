from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import main


def _show_startup_error(exc: Exception) -> None:
    application = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.critical(
        None,
        "CountWords",
        f"Falha ao iniciar a aplicacao:\n\n{exc}",
    )
    application.quit()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # pragma: no cover - launcher de interface
        _show_startup_error(error)
