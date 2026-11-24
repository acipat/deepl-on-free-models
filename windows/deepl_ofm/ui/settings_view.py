"""Settings dialog: provider, generation, behaviour, shortcuts and About.

The Swift app edits its settings live in a single scrolling page; the Windows
port uses a tabbed dialog with an explicit Save/Cancel contract.  Values are
loaded into the widgets when the dialog opens, written back to
:class:`~deepl_ofm.core.settings.AppSettings` on Save, and restored on Cancel.
All colours, fonts and component chrome come from the shared design system.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QRectF, QSignalBlocker, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..core.keycombo import KeyCombo
from ..core.languages import AppLanguage, get_language
from ..core.prompts import PromptBuilder, TranslationStyle, TranslationTone
from ..core.providers import Provider
from ..core.settings import AppSettings
from ..i18n import t, tf
from ..services import startup
from ..services.startup import StartupError, StartupStatus
from . import icons
from .catalog_view import CatalogView
from .components import (
    Card,
    Divider,
    FormRow,
    LanguageCombo,
    LinkButton,
    PrimaryButton,
    SearchField,
    SecondaryButton,
    StyleChips,
    ToneChips,
    ToggleRow,
)
from .theme import Theme

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..controller import AppController

log = logging.getLogger(__name__)

GITHUB_URL = "https://github.com/Lexus2016/deepl-on-free-models"

_INVALID_HOTKEY_HINT = "At least one of Ctrl or Alt is required."


# ---------------------------------------------------------------------------
# Small widgets


class _RoleLabel(QLabel):
    """QLabel tinted with a palette role and refreshed on theme changes."""

    def __init__(
        self,
        text: str = "",
        role: str = "text",
        size: int = 12,
        weight: int = 400,
        parent: QWidget | None = None,
        *,
        mono: bool = False,
    ) -> None:
        super().__init__(text, parent)
        self._role = role
        self.setFont(Theme.font(size, weight, mono=mono))
        Theme.changed.connect(self._sync_colour)
        self._sync_colour()

    def set_role(self, role: str) -> None:
        self._role = role
        self._sync_colour()

    def _sync_colour(self, *_args: object) -> None:
        colour = getattr(Theme.palette(), self._role, Theme.palette().text)
        self.setStyleSheet(f"color: {colour};")


class _SliderField(QWidget):
    """A QSlider mapped onto a floating-point range with a live value label."""

    changed = Signal(float)

    def __init__(
        self,
        minimum: float,
        maximum: float,
        step: float,
        value: float,
        parent: QWidget | None = None,
        *,
        decimals: int = 2,
        suffix: str = "",
    ) -> None:
        super().__init__(parent)
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self._step = float(step) if step else 1.0
        self._decimals = int(decimals)
        self._suffix = suffix
        self._steps = max(1, int(round((self._maximum - self._minimum) / self._step)))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setMinimum(0)
        self.slider.setMaximum(self._steps)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(max(1, self._steps // 10))
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.slider, 1)

        self.value_label = _RoleLabel("", "text", 11, parent=self, mono=True)
        self.value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.value_label.setFixedWidth(64)
        layout.addWidget(self.value_label, 0)

        self._value = self._minimum
        self._refresh(self.slider.value())
        self.slider.valueChanged.connect(self._on_slider)

    # -- value --------------------------------------------------------------
    def value(self) -> float:
        return self._value

    def set_value(self, value: float) -> None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = self._minimum
        numeric = max(self._minimum, min(self._maximum, numeric))
        index = int(round((numeric - self._minimum) / self._step))
        index = max(0, min(self._steps, index))
        self.slider.blockSignals(True)
        try:
            self.slider.setValue(index)
        finally:
            self.slider.blockSignals(False)
        self._refresh(index)

    def _on_slider(self, index: int) -> None:
        self._refresh(index)
        self.changed.emit(self._value)

    def _refresh(self, index: int) -> None:
        numeric = self._minimum + int(index) * self._step
        if self._decimals <= 0:
            self._value = float(int(round(numeric)))
            text = f"{int(self._value):,}".replace(",", " ")
        else:
            self._value = round(numeric, self._decimals)
            text = f"{self._value:.{self._decimals}f}"
        self.value_label.setText(text + self._suffix)
        self.slider.setToolTip(text + self._suffix)


class _ApiKeyField(QWidget):
    """Password field with a reveal toggle and an optional provider key link."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._key_url: str | None = None
        self._revealed = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.line = QLineEdit(self)
        self.line.setEchoMode(QLineEdit.EchoMode.Password)
        self.line.setFont(Theme.font(12, 400, mono=True))
        self.line.setMinimumHeight(34)
        layout.addWidget(self.line, 1)

        self.reveal_button = LinkButton(t("Show"), self)
        self.reveal_button.setObjectName("apiKeyReveal")
        self.reveal_button.setToolTip(t("Show"))
        self.reveal_button.clicked.connect(self._toggle_reveal)
        layout.addWidget(self.reveal_button)

        self.key_link = LinkButton(t("Get key ↗"), self)
        self.key_link.setObjectName("apiKeyLink")
        self.key_link.setVisible(False)
        self.key_link.clicked.connect(self._open_key_url)
        layout.addWidget(self.key_link)

    # -- value --------------------------------------------------------------
    def value(self) -> str:
        return self.line.text().strip()

    def set_value(self, value: str) -> None:
        self.line.setText(value or "")

    def set_provider(self, provider: Provider) -> None:
        self._key_url = provider.key_url if provider.requires_key else None
        self.key_link.setVisible(bool(self._key_url))

    def _toggle_reveal(self) -> None:
        self._revealed = not self._revealed
        self.line.setEchoMode(
            QLineEdit.EchoMode.Normal
            if self._revealed
            else QLineEdit.EchoMode.Password
        )
        self.reveal_button.setText(t("Hide") if self._revealed else t("Show"))

    def _open_key_url(self) -> None:
        if self._key_url:
            QDesktopServices.openUrl(QUrl(self._key_url))

    def retranslate_ui(self) -> None:
        self.key_link.setText(t("Get key ↗"))
        self.reveal_button.setText(t("Hide") if self._revealed else t("Show"))
        self.reveal_button.setToolTip(self.reveal_button.text())


class _HotkeyEdit(QKeySequenceEdit):
    """Key-sequence editor that reports focus changes for the idle caption."""

    focusChanged = Signal(bool)

    def focusInEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        super().focusInEvent(event)
        self.focusChanged.emit(True)

    def focusOutEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        super().focusOutEvent(event)
        self.focusChanged.emit(False)


class _InstallCommandBox(QWidget):
    """Compact read-only install command with a copy link.

    Matches the catalogue's command box without importing its private widget,
    which belongs to a dialog the settings page does not otherwise depend on.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("installCommandBox")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 6, 5)
        layout.setSpacing(8)

        self.command_label = _RoleLabel("", "muted", 10, parent=self, mono=True)
        self.command_label.setWordWrap(True)
        self.command_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.command_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.command_label, 1)

        self.copy_button = LinkButton(t("Copy install command"), self)
        self.copy_button.setObjectName("copyInstallCommandButton")
        self.copy_button.clicked.connect(self._copy)
        layout.addWidget(self.copy_button, 0, Qt.AlignmentFlag.AlignTop)

        Theme.changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, *_args: object) -> None:
        self.update()

    def command(self) -> str:
        return self.command_label.text()

    def set_command(self, command: str) -> None:
        self.command_label.setText(command or "")
        self.copy_button.setVisible(bool(command))

    def _copy(self) -> None:
        if self.command():
            QGuiApplication.clipboard().setText(self.command())

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            painter.setBrush(QColor(palette.card_hover))
            painter.setPen(QColor(palette.border))
            painter.drawRoundedRect(rect, 7.0, 7.0)
        finally:
            painter.end()

    def retranslate_ui(self) -> None:
        self.copy_button.setText(t("Copy install command"))
        self.updateGeometry()


# ---------------------------------------------------------------------------
# Dialog


def _voice_language_matches(locale: str, code: str) -> bool:
    """True when a Qt voice locale belongs to the given language code."""
    tag = (locale or "").lower().replace("-", "_")
    wanted = (code or "").lower().replace("-", "_")
    if not tag or not wanted or wanted == "auto":
        return False
    return tag == wanted or tag.startswith(wanted + "_")


class SettingsView(QDialog):
    """Tabbed settings dialog with a draft that is committed by Save."""

    def __init__(self, controller: "AppController", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._initial: dict[str, Any] = {}
        self._shown_once = False
        self._models_cache: list[str] = []
        self._fallback_models_cache: list[str] = []
        self._secret_backend = ""
        self._models_loading = False
        self._fallback_loading = False
        self._models_error = ""
        self._fallback_error = ""
        self._connect_hint_provider: Provider | None = None
        self._login_status = StartupStatus.UNSUPPORTED
        self._login_error_text = ""

        self.setWindowTitle(t("Settings"))
        self.setWindowIcon(icons.icon("settings", size=64))
        self.setObjectName("settingsView")
        self.setMinimumSize(680, 560)
        self.setFixedSize(760, 640)

        self._build_ui()
        self._connect_controller()
        self._apply_theme()
        self._load_from_settings(capture=True)
        self.retranslate_ui()
        self._refresh_open_at_login()
        Theme.changed.connect(self._apply_theme)

    # ------------------------------------------------------------------ ui
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(Divider("horizontal", self))

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("settingsTabs")
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.addTab(self._build_model_tab(), t("Model & provider").replace("&", "&&"))
        self.tabs.addTab(self._build_generation_tab(), t("Generation"))
        self.tabs.addTab(self._build_behaviour_tab(), t("Behavior"))
        self.tabs.addTab(self._build_hotkeys_tab(), t("Hot keys"))
        self.tabs.addTab(self._build_about_tab(), t("About"))
        root.addWidget(self.tabs, 1)

        root.addWidget(Divider("horizontal", self))
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        self.header = QWidget(self)
        self.header.setObjectName("settingsHeader")
        layout = QHBoxLayout(self.header)
        layout.setContentsMargins(22, 15, 22, 14)
        layout.setSpacing(10)

        self.title_label = _RoleLabel(t("Settings"), "text", 18, 600, self.header)
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.version_label = _RoleLabel(
            f"{APP_NAME} {__version__}", "faint", 11, parent=self.header
        )
        layout.addWidget(self.version_label)
        return self.header

    def _make_page(self, name: str) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
        scroll = QScrollArea(self.tabs)
        scroll.setObjectName(name)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget(scroll)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 10, 22, 16)
        layout.setSpacing(6)
        scroll.setWidget(page)
        return scroll, page, layout

    # -- model tab ---------------------------------------------------------
    def _build_model_tab(self) -> QWidget:
        scroll, page, page_layout = self._make_page("settingsModelPage")

        self.model_card = Card(
            t("Model and provider"),
            t(
                "Local models run offline and for free. Cloud models answer faster "
                "but need a key."
            ),
            page,
        )
        body = self.model_card.content_layout
        body.setSpacing(5)

        self.provider_combo = QComboBox(self.model_card)
        self.provider_combo.setObjectName("providerCombo")
        self.provider_combo.setMinimumHeight(34)
        self.provider_combo.setAccessibleName(t("Provider"))
        self.provider_combo.currentIndexChanged.connect(self._on_primary_provider_changed)

        self.provider_row = FormRow(t("Provider"), self.provider_combo, parent=self.model_card)
        self.model_card.add(self.provider_row)

        self.provider_detail = _RoleLabel("", "muted", 11.5, parent=self.model_card)
        self.provider_detail.setWordWrap(True)
        self.model_card.add(self.provider_detail)

        self.base_url_edit = QLineEdit(self.model_card)
        self.base_url_edit.setObjectName("baseUrlEdit")
        self.base_url_edit.setFont(Theme.font(12, 400, mono=True))
        self.base_url_edit.setMinimumHeight(34)
        self.address_row = FormRow(t("Server address"), self.base_url_edit, parent=self.model_card)
        self.model_card.add(self.address_row)

        self.api_key_field = _ApiKeyField(self.model_card)
        self.api_key_field.line.setObjectName("apiKeyEdit")
        self.api_key_edit = self.api_key_field.line
        self.api_key_fill = FormRow(
            t("API key"), self.api_key_field, parent=self.model_card
        )
        self.api_key_row = self.api_key_fill
        self.model_card.add(self.api_key_fill)

        self.model_edit = QLineEdit(self.model_card)
        self.model_edit.setObjectName("modelEdit")
        self.model_edit.setFont(Theme.font(12, 400, mono=True))
        self.model_edit.setMinimumHeight(34)
        self.model_edit.textChanged.connect(self._on_model_text_changed)
        model_host = QWidget(self.model_card)
        model_layout = QHBoxLayout(model_host)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(8)
        model_layout.addWidget(self.model_edit, 1)
        self.catalog_button = SecondaryButton(
            t("Model catalog…"), model_host, icon_name="sparkles"
        )
        self.catalog_button.setObjectName("modelCatalogButton")
        self.catalog_button.clicked.connect(self._open_catalog)
        model_layout.addWidget(self.catalog_button)
        self.model_row = FormRow(t("Model"), model_host, parent=self.model_card)
        self.model_card.add(self.model_row)

        connect_host = QWidget(self.model_card)
        connect_layout = QHBoxLayout(connect_host)
        connect_layout.setContentsMargins(0, 2, 0, 0)
        connect_layout.setSpacing(10)
        self.connect_button = SecondaryButton(
            t("Connect"), connect_host, icon_name="refresh"
        )
        self.connect_button.setObjectName("connectButton")
        self.connect_button.clicked.connect(self._connect_models)
        connect_layout.addWidget(self.connect_button)
        self.connect_status = _RoleLabel("", "muted", 11.5, parent=connect_host)
        self.connect_status.setWordWrap(True)
        connect_layout.addWidget(self.connect_status, 1)
        self.model_card.add(connect_host)

        self.install_row = _InstallCommandBox(self.model_card)
        self.install_command_label = self.install_row.command_label
        self.install_copy_button = self.install_row.copy_button
        self.install_row.setVisible(False)
        self.model_card.add(self.install_row)

        self.model_card.add(Divider("horizontal", self.model_card))

        models_header = QWidget(self.model_card)
        header_layout = QHBoxLayout(models_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        self.models_title_label = _RoleLabel(
            t("Models on the server"), "text", 12, 600, models_header
        )
        header_layout.addWidget(self.models_title_label)
        self.models_refresh = LinkButton(t("Refresh"), models_header)
        self.models_refresh.setObjectName("refreshModelsButton")
        self.models_refresh.setToolTip(t("Refresh"))
        self.models_refresh.clicked.connect(self._refresh_models)
        header_layout.addWidget(self.models_refresh)
        header_layout.addStretch(1)
        self.models_count_label = _RoleLabel(
            "", "faint", 11, parent=models_header, mono=True
        )
        header_layout.addWidget(self.models_count_label)
        self.model_card.add(models_header)

        self.model_filter = SearchField(t("Filter by name"), self.model_card)
        self.model_filter.setObjectName("modelFilter")
        self.model_filter.textChanged.connect(lambda _text: self._refresh_model_list())
        self.model_card.add(self.model_filter)

        self.models_list = QListWidget(self.model_card)
        self.models_list.setObjectName("modelsList")
        self.models_list.setMinimumHeight(210)
        self.models_list.setMaximumHeight(210)
        self.models_list.setFont(Theme.font(11, 400, mono=True))
        self.models_list.setAlternatingRowColors(False)
        self.models_list.setUniformItemSizes(True)
        self.models_list.itemClicked.connect(self._on_model_clicked)
        self.model_card.add(self.models_list)

        self.models_hint = _RoleLabel("", "muted", 11, parent=self.model_card)
        self.models_hint.setWordWrap(True)
        self.model_card.add(self.models_hint)

        self.models_error_label = _RoleLabel("", "danger", 11, parent=self.model_card)
        self.models_error_label.setWordWrap(True)
        self.models_error_label.setVisible(False)
        self.model_card.add(self.models_error_label)

        page_layout.addWidget(self.model_card)
        page_layout.addWidget(self._build_fallback_card(page))
        page_layout.addStretch(1)
        return scroll

    def _build_fallback_card(self, page: QWidget) -> Card:
        self.fallback_card = Card(
            t("Fallback provider"),
            t("Used automatically when the primary provider fails."),
            page,
        )
        body = self.fallback_card.content_layout
        body.setSpacing(10)

        self.fallback_toggle = ToggleRow(
            t("Use a fallback provider"), False, self.fallback_card
        )
        self.fallback_toggle.setObjectName("fallbackEnabledToggle")
        self.fallback_toggle.toggled.connect(lambda _checked: self._sync_fallback_body())
        self.fallback_card.add(self.fallback_toggle)

        self.fallback_body = QWidget(self.fallback_card)
        body_layout = QVBoxLayout(self.fallback_body)
        body_layout.setContentsMargins(0, 2, 0, 0)
        body_layout.setSpacing(8)

        self.fallback_provider_combo = QComboBox(self.fallback_body)
        self.fallback_provider_combo.setObjectName("fallbackProviderCombo")
        self.fallback_provider_combo.setMinimumHeight(34)
        self.fallback_provider_combo.setAccessibleName(t("Provider"))
        self.fallback_provider_combo.currentIndexChanged.connect(
            self._on_fallback_provider_changed
        )
        self.fallback_provider_row = FormRow(
            t("Provider"), self.fallback_provider_combo, parent=self.fallback_body
        )
        body_layout.addWidget(self.fallback_provider_row)

        self.fallback_base_edit = QLineEdit(self.fallback_body)
        self.fallback_base_edit.setObjectName("fallbackBaseUrlEdit")
        self.fallback_base_edit.setFont(Theme.font(12, 400, mono=True))
        self.fallback_base_edit.setMinimumHeight(34)
        self.fallback_address_row = FormRow(
            t("Server address"), self.fallback_base_edit, parent=self.fallback_body
        )
        body_layout.addWidget(self.fallback_address_row)

        self.fallback_key_field = _ApiKeyField(self.fallback_body)
        self.fallback_key_field.line.setObjectName("fallbackApiKeyEdit")
        self.fallback_key_row = FormRow(
            t("API key"), self.fallback_key_field, parent=self.fallback_body
        )
        self.fallback_api_key_row = self.fallback_key_row
        body_layout.addWidget(self.fallback_key_row)

        self.fallback_model_combo = QComboBox(self.fallback_body)
        self.fallback_model_combo.setObjectName("fallbackModelCombo")
        self.fallback_model_combo.setEditable(True)
        self.fallback_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.fallback_model_combo.setMinimumHeight(34)
        self.fallback_model_combo.lineEdit().setPlaceholderText(t("Choose a model"))
        self.fallback_model_combo.setFont(Theme.font(12, 400, mono=True))
        self.fallback_model_row = FormRow(
            t("Model"), self.fallback_model_combo, parent=self.fallback_body
        )
        body_layout.addWidget(self.fallback_model_row)

        load_row = QWidget(self.fallback_body)
        load_layout = QHBoxLayout(load_row)
        load_layout.setContentsMargins(0, 0, 0, 0)
        load_layout.setSpacing(10)
        self.load_fallback_button = SecondaryButton(
            t("Load models"), load_row, icon_name="refresh"
        )
        self.load_fallback_button.setObjectName("loadFallbackModelsButton")
        self.load_fallback_button.clicked.connect(self._load_fallback_models)
        load_layout.addWidget(self.load_fallback_button)
        self.fallback_status = _RoleLabel("", "muted", 11, parent=load_row)
        self.fallback_status.setWordWrap(True)
        load_layout.addWidget(self.fallback_status, 1)
        body_layout.addWidget(load_row)

        self.fallback_hint_label = _RoleLabel(
            t(
                "If the primary provider fails, the same text is retried with "
                "these settings."
            ),
            "faint",
            11,
            parent=self.fallback_body,
        )
        self.fallback_hint_label.setWordWrap(True)
        body_layout.addWidget(self.fallback_hint_label)

        self.fallback_card.add(self.fallback_body)
        return self.fallback_card

    # -- generation tab ----------------------------------------------------
    def _build_generation_tab(self) -> QWidget:
        scroll, page, page_layout = self._make_page("settingsGenerationPage")

        self.generation_card = Card(
            t("Generation parameters"),
            t("Defaults match Tencent’s recommendations for Hy-MT2 7B."),
            page,
        )
        body = self.generation_card.content_layout
        body.setSpacing(3)

        self.temperature_field = _SliderField(0.0, 1.5, 0.05, 0.7, self.generation_card)
        self.temperature_field.slider.setObjectName("temperatureSlider")
        self.temperature_slider = self.temperature_field.slider
        self.temperature_row = FormRow(
            t("Temperature"), self.temperature_field, parent=self.generation_card
        )
        self.generation_card.add(self.temperature_row)

        self.top_p_field = _SliderField(0.1, 1.0, 0.05, 0.6, self.generation_card)
        self.top_p_field.slider.setObjectName("topPSlider")
        self.top_p_slider = self.top_p_field.slider
        self.top_p_row = FormRow("Top-p", self.top_p_field, parent=self.generation_card)
        self.generation_card.add(self.top_p_row)

        self.top_k_field = _SliderField(
            1, 100, 1, 20, self.generation_card, decimals=0
        )
        self.top_k_field.slider.setObjectName("topKSlider")
        self.top_k_slider = self.top_k_field.slider
        self.top_k_row = FormRow("Top-k", self.top_k_field, parent=self.generation_card)
        self.generation_card.add(self.top_k_row)

        self.repetition_field = _SliderField(
            1.0, 1.5, 0.01, 1.05, self.generation_card
        )
        self.repetition_field.slider.setObjectName("repetitionSlider")
        self.repetition_slider = self.repetition_field.slider
        self.repetition_row = FormRow(
            t("Repetition"), self.repetition_field, parent=self.generation_card
        )
        self.generation_card.add(self.repetition_row)

        self.context_field = _SliderField(
            2048, 32768, 512, 8192, self.generation_card, decimals=0
        )
        self.context_field.slider.setObjectName("contextSlider")
        self.context_slider = self.context_field.slider
        self.context_row = FormRow(
            t("Context"), self.context_field, parent=self.generation_card
        )
        self.generation_card.add(self.context_row)

        page_layout.addWidget(self.generation_card)

        self.prompt_card = Card(
            t("System prompt"),
            t(
                "Hy-MT2 has no system prompt: instruction and text go in one "
                "message. Wording follows the model card."
            ),
            page,
        )
        prompt_body = self.prompt_card.content_layout
        prompt_body.setSpacing(4)

        self.style_chips = StyleChips("auto", self.prompt_card)
        self.style_chips.setMaximumWidth(340)
        self.style_row = FormRow(t("Style"), self.style_chips, parent=self.prompt_card)
        self.prompt_card.add(self.style_row)
        self.style_chips.changed.connect(lambda _value: self._update_preview())

        self.tone_chips = ToneChips("standard", self.prompt_card)
        self.tone_chips.setMaximumWidth(460)
        self.tone_row = FormRow(t("Tone"), self.tone_chips, parent=self.prompt_card)
        self.prompt_card.add(self.tone_row)
        self.tone_chips.changed.connect(lambda _value: self._update_preview())

        self.target_combo = LanguageCombo(False, self.prompt_card)
        self.target_combo.setMinimumWidth(220)
        self.target_combo.setMaximumWidth(320)
        self.target_row = FormRow(
            t("Translate to"), self.target_combo, parent=self.prompt_card
        )
        self.prompt_card.add(self.target_row)
        self.target_combo.code_changed.connect(lambda _code: self._update_preview())

        self.prompt_preview = QPlainTextEdit(self.prompt_card)
        self.prompt_preview.setObjectName("promptPreview")
        self.prompt_preview.setReadOnly(True)
        self.prompt_preview.setFont(Theme.font(10, 400, mono=True))
        self.prompt_preview.setFixedHeight(78)
        self.prompt_preview.setFrameShape(QFrame.Shape.NoFrame)
        self.prompt_preview.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.prompt_preview.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.prompt_card.add(self.prompt_preview)

        page_layout.addWidget(self.prompt_card)
        page_layout.addStretch(1)
        return scroll

    # -- behaviour tab -----------------------------------------------------
    def _build_behaviour_tab(self) -> QWidget:
        scroll, page, page_layout = self._make_page("settingsBehaviourPage")

        self.behaviour_card = Card(t("Behavior"), "", page)
        body = self.behaviour_card.content_layout
        body.setSpacing(10)

        self.auto_toggle = ToggleRow(
            t("Translate automatically while typing"), False, self.behaviour_card
        )
        self.auto_toggle.setObjectName("autoTranslateToggle")
        self.auto_toggle.toggled.connect(self._sync_debounce_visibility)
        self.behaviour_card.add(self.auto_toggle)

        self.debounce_field = _SliderField(
            0.2, 2.0, 0.05, 0.45, self.behaviour_card, suffix=" s"
        )
        self.debounce_field.slider.setObjectName("debounceSlider")
        self.debounce_slider = self.debounce_field.slider
        self.debounce_row = FormRow(
            t("Delay"), self.debounce_field, parent=self.behaviour_card
        )
        self.behaviour_card.add(self.debounce_row)

        self.translate_in_one_request_toggle = ToggleRow(
            t("Translate text in one request"), False, self.behaviour_card
        )
        self.translate_in_one_request_toggle.setObjectName("translateInOneRequestToggle")
        self.behaviour_card.add(self.translate_in_one_request_toggle)

        self.keep_history_toggle = ToggleRow(
            t("Keep translation history"), False, self.behaviour_card
        )
        self.keep_history_toggle.setObjectName("keepHistoryToggle")
        self.behaviour_card.add(self.keep_history_toggle)

        self.login_controls = QWidget(self.behaviour_card)
        login_layout = QVBoxLayout(self.login_controls)
        login_layout.setContentsMargins(0, 0, 0, 0)
        login_layout.setSpacing(5)

        self.login_toggle = ToggleRow(t("Open at login"), False, self.login_controls)
        self.login_toggle.setObjectName("openAtLoginToggle")
        self.login_toggle.toggled.connect(self._set_open_at_login)
        login_layout.addWidget(self.login_toggle)

        self.login_error = _RoleLabel("", "danger", 11, parent=self.login_controls)
        self.login_error.setWordWrap(True)
        self.login_error.setVisible(False)
        login_layout.addWidget(self.login_error)

        self.login_approval = QWidget(self.login_controls)
        approval_layout = QVBoxLayout(self.login_approval)
        approval_layout.setContentsMargins(0, 0, 0, 0)
        approval_layout.setSpacing(5)
        self.login_hint = _RoleLabel(
            t("Allow DeepL-oFM to open at login in System Settings."),
            "muted",
            11,
            parent=self.login_approval,
        )
        self.login_hint.setWordWrap(True)
        approval_layout.addWidget(self.login_hint)
        self.login_settings_button = SecondaryButton(
            t("Open System Settings"), self.login_approval
        )
        self.login_settings_button.setObjectName("openLoginSettingsButton")
        self.login_settings_button.setFixedHeight(28)
        self.login_settings_button.setFont(Theme.font(11, 500))
        self.login_settings_button.clicked.connect(self._open_login_settings)
        approval_layout.addWidget(
            self.login_settings_button, 0, Qt.AlignmentFlag.AlignLeft
        )
        self.login_approval.setVisible(False)
        login_layout.addWidget(self.login_approval)

        self.behaviour_card.add(self.login_controls)

        self.warm_up_toggle = ToggleRow(
            t("Load the translator at launch"),
            False,
            self.behaviour_card,
            hint=t(
                "Connects to the provider, refreshes the model list and warms up "
                "a local model."
            ),
        )
        self.warm_up_toggle.setObjectName("warmUpToggle")
        self.behaviour_card.add(self.warm_up_toggle)

        self.behaviour_card.add(Divider("horizontal", self.behaviour_card))

        self.language_combo = QComboBox(self.behaviour_card)
        self.language_combo.setObjectName("interfaceLanguageCombo")
        self.language_combo.setMinimumHeight(34)
        self.language_combo.setAccessibleName(t("Interface language"))
        self.language_row = FormRow(
            t("Interface language"), self.language_combo, parent=self.behaviour_card
        )
        self.behaviour_card.add(self.language_row)

        self.tray_toggle = ToggleRow(
            t("Tray icon"),
            False,
            self.behaviour_card,
            hint=t("Keep DeepL-oFM in the notification area; closing the window then hides it."),
        )
        self.tray_toggle.setObjectName("trayToggle")
        self.behaviour_card.add(self.tray_toggle)

        self.voice_combo = QComboBox(self.behaviour_card)
        self.voice_combo.setObjectName("speechVoiceCombo")
        self.voice_combo.setMinimumHeight(34)
        self.voice_combo.setAccessibleName(t("Voice"))
        self.voice_row = FormRow(
            t("Voice"),
            self.voice_combo,
            t("More voices can be added in Windows Settings → Time & language → Speech."),
            parent=self.behaviour_card,
        )
        self.behaviour_card.add(self.voice_row)
        self._populate_voices()

        page_layout.addWidget(self.behaviour_card)
        page_layout.addStretch(1)
        return scroll

    def _reset_hotkey(self) -> None:
        from ..core.keycombo import KeyCombo

        self._set_hotkey_edit(self.hotkey_edit, KeyCombo.standard())
        self._validate_hotkey(self.hotkey_edit, self.hotkey_row)
        self._sync_hotkey_caption(self.hotkey_edit)

    def _reset_selection_hotkey(self) -> None:
        from ..core.keycombo import KeyCombo

        self._set_hotkey_edit(self.selection_hotkey_edit, KeyCombo.selection())
        self._validate_hotkey(self.selection_hotkey_edit, self.selection_hotkey_row)
        self._sync_hotkey_caption(self.selection_hotkey_edit)

    def _sync_hotkey_status(self) -> None:
        """Show whether the system actually accepted each shortcut."""
        controller = self.controller
        combos = (
            (self.hotkey_status, getattr(controller, "hotkey_message", "")),
            (self.selection_hotkey_status, getattr(controller, "selection_hotkey_message", "")),
        )
        for label, message in combos:
            if message:
                label.setText(message)
                label.setProperty("role", "danger")
            else:
                label.setText(t("Active"))
                label.setProperty("role", "success")
            label.style().unpolish(label)
            label.style().polish(label)

    def _sync_debounce_visibility(self, checked: bool) -> None:
        """The delay slider only matters while automatic translation is on."""
        self.debounce_row.setVisible(bool(checked))

    # -- open at login -----------------------------------------------------
    def _refresh_open_at_login(self) -> None:
        """Read the OS state; unsupported platforms hide the whole row."""
        try:
            status = StartupStatus(startup.status())
        except Exception:  # noqa: BLE001 - a service bug must not break Settings
            log.exception("could not read the Open at login status")
            status = StartupStatus.DISABLED
        if status is not self._login_status:
            self._login_error_text = ""
        self._login_status = status
        if status is StartupStatus.UNSUPPORTED:
            self.login_controls.setVisible(False)
            return

        self.login_controls.setVisible(True)
        self._apply_toggle(self.login_toggle, status is StartupStatus.ENABLED)
        self.login_approval.setVisible(status is StartupStatus.REQUIRES_APPROVAL)
        self.login_error.setText(self._login_error_text)
        self.login_error.setVisible(bool(self._login_error_text))

    def _set_open_at_login(self, enabled: bool) -> None:
        """Apply a toggle change, mirroring ``setLoginItemEnabled`` in Swift."""
        self._refresh_open_at_login()
        self._login_error_text = ""
        self.login_error.setText("")
        self.login_error.setVisible(False)

        if enabled == (self._login_status is StartupStatus.ENABLED):
            return
        if self._login_status is StartupStatus.REQUIRES_APPROVAL:
            self._open_login_settings()
            return

        try:
            startup.set_enabled(enabled)
        except StartupError as error:
            log.warning("could not change Open at login: %s", error)
            self._refresh_open_at_login()
            if (
                self._login_status is not StartupStatus.REQUIRES_APPROVAL
                and enabled != (self._login_status is StartupStatus.ENABLED)
            ):
                self._login_error_text = str(error)
                self.login_error.setText(self._login_error_text)
                self.login_error.setVisible(True)
            return
        except Exception:  # noqa: BLE001 - a service bug must not close the dialog
            log.exception("unexpected Open at login failure")
            self._refresh_open_at_login()
            return

        self._refresh_open_at_login()

    def _open_login_settings(self) -> None:
        if not startup.open_settings():
            log.warning("could not open the system login-item settings")

    def _on_application_state_changed(self, state: Qt.ApplicationState) -> None:
        """Pick up a change made in System Settings when the app is activated."""
        if state == Qt.ApplicationState.ApplicationActive and self.isVisible():
            self._refresh_open_at_login()

    def _populate_voices(self) -> None:
        """List the voices for the current target language, like the macOS app.

        The stored voice stays selectable even when it does not match the
        language, so opening the dialog never silently drops a choice.
        """
        combo = self.voice_combo
        chosen = str(combo.currentData() or "") or self.controller.settings.speech_voice_id
        target = self.controller.target_language
        code = getattr(target, "code", "") if target is not None else ""

        with QSignalBlocker(combo):
            combo.clear()
            combo.addItem(t("Automatic"), "")
            listed: set[str] = set()
            try:
                from ..services.speech import Speaker

                if getattr(self, "_speaker", None) is None:
                    self._speaker = Speaker(self)
                for voice_id, label in self._speaker.voices():
                    locale = voice_id.split("::", 1)[0] if "::" in voice_id else ""
                    matches = _voice_language_matches(locale, code)
                    if code and code != "auto" and not matches and voice_id != chosen:
                        continue
                    combo.addItem(f"{label} — {locale.replace('_', '-')}" if locale else label, voice_id)
                    listed.add(voice_id)
            except Exception:  # noqa: BLE001 - speech is optional
                pass
            if chosen and chosen not in listed:
                combo.addItem(chosen.split("::", 1)[-1], chosen)
            index = combo.findData(chosen)
            if index >= 0:
                combo.setCurrentIndex(index)

    # -- hotkeys tab -------------------------------------------------------
    def _build_hotkeys_tab(self) -> QWidget:
        scroll, page, page_layout = self._make_page("settingsHotkeysPage")

        self.hotkey_card = Card(
            t("Hot key"),
            t(
                "Copy text anywhere and press the shortcut — DeepL-oFM opens and "
                "translates the clipboard."
            ),
            page,
        )
        body = self.hotkey_card.content_layout
        body.setSpacing(10)

        self.hotkey_edit = _HotkeyEdit(self.hotkey_card)
        self.hotkey_edit.setObjectName("hotkeyEdit")
        self.hotkey_edit.setMinimumHeight(34)
        self.hotkey_edit.setClearButtonEnabled(True)
        self.hotkey_status = _RoleLabel("", "muted", 11, parent=self.hotkey_card)
        self.hotkey_status.setWordWrap(True)
        self.hotkey_reset = LinkButton(t("Reset"), self.hotkey_card)
        self.hotkey_reset.clicked.connect(self._reset_hotkey)
        hotkey_control = QWidget(self.hotkey_card)
        hotkey_control_layout = QHBoxLayout(hotkey_control)
        hotkey_control_layout.setContentsMargins(0, 0, 0, 0)
        hotkey_control_layout.setSpacing(8)
        hotkey_control_layout.addWidget(self.hotkey_edit, 1)
        self.hotkey_caption = _RoleLabel(
            "", "muted", 11, 500, parent=hotkey_control, mono=True
        )
        self.hotkey_caption.setMinimumWidth(120)
        hotkey_control_layout.addWidget(self.hotkey_caption, 0)
        hotkey_control_layout.addWidget(self.hotkey_reset, 0)
        self.hotkey_row = FormRow(
            t("Translate clipboard"), hotkey_control, parent=self.hotkey_card
        )
        self.hotkey_card.add(self.hotkey_row)
        self.hotkey_card.add(self.hotkey_status)
        self.hotkey_edit.keySequenceChanged.connect(
            lambda _seq: self._validate_hotkey(self.hotkey_edit, self.hotkey_row)
        )
        self.hotkey_edit.keySequenceChanged.connect(
            lambda _seq: self._sync_hotkey_caption(self.hotkey_edit)
        )
        self.hotkey_edit.focusChanged.connect(
            lambda _focused: self._sync_hotkey_caption(self.hotkey_edit)
        )

        self.selection_hotkey_edit = _HotkeyEdit(self.hotkey_card)
        self.selection_hotkey_edit.setObjectName("selectionHotkeyEdit")
        self.selection_hotkey_edit.setMinimumHeight(34)
        self.selection_hotkey_edit.setClearButtonEnabled(True)
        self.selection_hotkey_status = _RoleLabel("", "muted", 11, parent=self.hotkey_card)
        self.selection_hotkey_status.setWordWrap(True)
        self.selection_hotkey_reset = LinkButton(t("Reset"), self.hotkey_card)
        self.selection_hotkey_reset.clicked.connect(self._reset_selection_hotkey)
        selection_control = QWidget(self.hotkey_card)
        selection_control_layout = QHBoxLayout(selection_control)
        selection_control_layout.setContentsMargins(0, 0, 0, 0)
        selection_control_layout.setSpacing(8)
        selection_control_layout.addWidget(self.selection_hotkey_edit, 1)
        self.selection_hotkey_caption = _RoleLabel(
            "", "muted", 11, 500, parent=selection_control, mono=True
        )
        self.selection_hotkey_caption.setMinimumWidth(120)
        selection_control_layout.addWidget(self.selection_hotkey_caption, 0)
        selection_control_layout.addWidget(self.selection_hotkey_reset, 0)
        self.selection_hotkey_row = FormRow(
            t("Selected text"),
            selection_control,
            parent=self.hotkey_card,
        )
        self.hotkey_card.add(self.selection_hotkey_row)
        self.hotkey_card.add(self.selection_hotkey_status)
        self.selection_hotkey_edit.keySequenceChanged.connect(
            lambda _seq: self._validate_hotkey(
                self.selection_hotkey_edit, self.selection_hotkey_row
            )
        )
        self.selection_hotkey_edit.keySequenceChanged.connect(
            lambda _seq: self._sync_hotkey_caption(self.selection_hotkey_edit)
        )
        self.selection_hotkey_edit.focusChanged.connect(
            lambda _focused: self._sync_hotkey_caption(self.selection_hotkey_edit)
        )

        self.hotkey_hint = _RoleLabel(
            t(
                "Select text in any app and press the shortcut — DeepL-oFM copies "
                "it and translates."
            ),
            "muted",
            11,
            parent=self.hotkey_card,
        )
        self.hotkey_hint.setWordWrap(True)
        self.hotkey_card.add(self.hotkey_hint)

        self.hotkey_examples = _RoleLabel(
            t("Examples: Ctrl+Alt+T or Ctrl+Alt+C."),
            "faint",
            11,
            parent=self.hotkey_card,
        )
        self.hotkey_card.add(self.hotkey_examples)

        page_layout.addWidget(self.hotkey_card)
        page_layout.addStretch(1)
        return scroll

    # -- about tab ---------------------------------------------------------
    def _build_about_tab(self) -> QWidget:
        scroll, page, page_layout = self._make_page("settingsAboutPage")

        self.about_card = Card(t("About"), "", page)
        body = self.about_card.content_layout
        body.setSpacing(8)

        name_row = QWidget(self.about_card)
        name_layout = QHBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(8)
        self.about_name = _RoleLabel(APP_NAME, "text", 15, 600, name_row)
        name_layout.addWidget(self.about_name)
        self.about_version = _RoleLabel(
            f"Version {__version__}", "faint", 11, parent=name_row, mono=True
        )
        name_layout.addWidget(self.about_version)
        name_layout.addStretch(1)
        self.about_card.add(name_row)

        self.about_description = _RoleLabel(
            t("A native translator for local and cloud models."),
            "muted",
            12,
            parent=self.about_card,
        )
        self.about_description.setWordWrap(True)
        self.about_card.add(self.about_description)

        self.about_license = _RoleLabel(
            t("MIT license · free and open source."), "faint", 11, parent=self.about_card
        )
        self.about_card.add(self.about_license)

        self.model_license = _RoleLabel(
            t("Model: Hy-MT2 7B (Tencent Hy). License and model card on Hugging Face."),
            "faint",
            11,
            parent=self.about_card,
        )
        self.model_license.setWordWrap(True)
        self.about_card.add(self.model_license)

        self.huggingface_button = LinkButton(
            "huggingface.co/tencent/Hy-MT2-7B", self.about_card
        )
        self.huggingface_button.setObjectName("huggingFaceButton")
        self.huggingface_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://huggingface.co/tencent/Hy-MT2-7B")
            )
        )
        huggingface_host = QWidget(self.about_card)
        huggingface_layout = QHBoxLayout(huggingface_host)
        huggingface_layout.setContentsMargins(0, 0, 0, 0)
        huggingface_layout.addWidget(self.huggingface_button, 0)
        huggingface_layout.addStretch(1)
        self.about_card.add(huggingface_host)

        github_host = QWidget(self.about_card)
        github_layout = QHBoxLayout(github_host)
        github_layout.setContentsMargins(0, 0, 0, 0)
        github_layout.setSpacing(0)
        self.github_button = LinkButton(t("DeepL-oFM on GitHub"), github_host)
        self.github_button.setObjectName("githubButton")
        self.github_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL))
        )
        github_layout.addWidget(self.github_button, 0)
        github_layout.addStretch(1)
        self.about_card.add(github_host)

        self.about_card.add(Divider("horizontal", self.about_card))

        self.settings_path_label = _RoleLabel("", "muted", 11, parent=self.about_card, mono=True)
        self.settings_path_label.setWordWrap(True)
        self.settings_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.settings_row = FormRow(
            t("Settings file"), self.settings_path_label, parent=self.about_card
        )
        self.about_card.add(self.settings_row)

        self.history_path_label = _RoleLabel("", "muted", 11, parent=self.about_card, mono=True)
        self.history_path_label.setWordWrap(True)
        self.history_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.history_row = FormRow(
            t("History file"), self.history_path_label, parent=self.about_card
        )
        self.about_card.add(self.history_row)

        self.key_backend_label = _RoleLabel("", "muted", 11, parent=self.about_card, mono=True)
        self.key_row = FormRow(
            t("Key storage"), self.key_backend_label, parent=self.about_card
        )
        self.about_card.add(self.key_row)

        page_layout.addWidget(self.about_card)
        page_layout.addStretch(1)
        return scroll

    def _build_footer(self) -> QWidget:
        self.footer = QWidget(self)
        self.footer.setObjectName("settingsFooter")
        layout = QHBoxLayout(self.footer)
        layout.setContentsMargins(22, 12, 18, 12)
        layout.setSpacing(10)

        self.footer_hint = _RoleLabel(
            t("Changes apply when you save."), "faint", 11, parent=self.footer
        )
        layout.addWidget(self.footer_hint)
        layout.addStretch(1)

        self.cancel_button = SecondaryButton(t("Cancel"), self.footer)
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)

        self.save_button = PrimaryButton(
            t("Save"), self.footer, icon_name="check"
        )
        self.save_button.setObjectName("saveButton")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save)
        layout.addWidget(self.save_button)
        return self.footer

    # -------------------------------------------------------------- signals
    def _connect_controller(self) -> None:
        controller = self.controller
        controller.modelsChanged.connect(self._on_models_changed)
        controller.modelsLoadingChanged.connect(self._on_models_loading)
        controller.modelsErrorChanged.connect(self._on_models_error)
        controller.fallbackModelsChanged.connect(self._on_fallback_models_changed)
        controller.fallbackModelsLoadingChanged.connect(self._on_fallback_loading)
        controller.fallbackModelsErrorChanged.connect(self._on_fallback_error)
        controller.backendStatusChanged.connect(lambda _status: self._sync_connect_status())
        controller.probeMessageChanged.connect(lambda _message: self._sync_connect_status())
        controller.interfaceLanguageChanged.connect(
            lambda _code: self.retranslate_ui()
        )
        controller.settingsChanged.connect(self._sync_connect_status)
        app = QGuiApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_application_state_changed)

    # ----------------------------------------------------------- load/save
    @staticmethod
    def _snapshot(settings: AppSettings) -> dict[str, Any]:
        return {
            "provider": settings.provider,
            "base_url": settings.base_url,
            "model": settings.model,
            "api_key": settings.api_key,
            "fallback_enabled": settings.fallback_enabled,
            "fallback_provider": settings.fallback_provider,
            "fallback_base_url": settings.fallback_base_url,
            "fallback_model": settings.fallback_model,
            "fallback_api_key": settings.fallback_api_key,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "top_k": settings.top_k,
            "repetition_penalty": settings.repetition_penalty,
            "context_window": settings.context_window,
            "auto_translate": settings.auto_translate,
            "translate_in_one_request": settings.translate_in_one_request,
            "debounce": settings.debounce,
            "keep_history": settings.keep_history,
            "warm_up_on_launch": settings.warm_up_on_launch,
            "show_in_menu_bar": settings.show_in_menu_bar,
            "interface_language": settings.interface_language,
            "speech_voice_id": settings.speech_voice_id,
            "hot_key": settings.hot_key,
            "selection_hot_key": settings.selection_hot_key,
        }

    def _load_from_settings(self, *, capture: bool = False) -> None:
        settings = self.controller.settings
        if capture or not self._initial:
            self._initial = self._snapshot(settings)

        with QSignalBlocker(self.provider_combo):
            self._fill_provider_combo(self.provider_combo, settings.provider)
        self.base_url_edit.setText(settings.base_url)
        self.model_edit.setText(settings.model)
        self.api_key_field.set_value(settings.api_key)
        self._sync_provider_widgets(settings.provider)

        self._apply_toggle(self.fallback_toggle, settings.fallback_enabled)
        with QSignalBlocker(self.fallback_provider_combo):
            self._fill_provider_combo(
                self.fallback_provider_combo, settings.fallback_provider
            )
        with QSignalBlocker(self.fallback_base_edit):
            self.fallback_base_edit.setText(settings.fallback_base_url)
        with QSignalBlocker(self.fallback_model_combo):
            self.fallback_model_combo.setEditText(settings.fallback_model)
        self.fallback_key_field.set_value(settings.fallback_api_key)
        self._sync_fallback_provider_widgets(settings.fallback_provider)
        self._sync_fallback_body()

        self.temperature_field.set_value(settings.temperature)
        self.top_p_field.set_value(settings.top_p)
        self.top_k_field.set_value(settings.top_k)
        self.repetition_field.set_value(settings.repetition_penalty)
        self.context_field.set_value(settings.context_window)

        self._apply_toggle(self.auto_toggle, settings.auto_translate)
        self._apply_toggle(
            self.translate_in_one_request_toggle, settings.translate_in_one_request
        )
        self._sync_debounce_visibility(settings.auto_translate)
        self.debounce_field.set_value(settings.debounce)
        self._apply_toggle(self.keep_history_toggle, settings.keep_history)
        self._apply_toggle(self.warm_up_toggle, settings.warm_up_on_launch)
        self._apply_toggle(self.tray_toggle, settings.show_in_menu_bar)
        with QSignalBlocker(self.language_combo):
            self._fill_language_combo(self.language_combo, settings.interface_language)
        self._populate_voices()
        index = self.voice_combo.findData(settings.speech_voice_id)
        with QSignalBlocker(self.voice_combo):
            self.voice_combo.setCurrentIndex(index if index >= 0 else 0)

        self.style_chips.set_value(self.controller.style.value)
        self.tone_chips.set_value(self.controller.tone.value)
        self.target_combo.set_code(self.controller.target_language.code)
        self._update_preview()

        self._set_hotkey_edit(self.hotkey_edit, settings.hot_key)
        self._sync_hotkey_status()
        self._set_hotkey_edit(self.selection_hotkey_edit, settings.selection_hot_key)
        self._validate_hotkey(self.hotkey_edit, self.hotkey_row)
        self._validate_hotkey(self.selection_hotkey_edit, self.selection_hotkey_row)
        self._sync_hotkey_caption(self.hotkey_edit)
        self._sync_hotkey_caption(self.selection_hotkey_edit)

        self._models_cache = list(self.controller.provider_models)
        self._fallback_models_cache = list(self.controller.fallback_models)
        self._models_loading = bool(self.controller.models_loading)
        self._fallback_loading = bool(self.controller.fallback_models_loading)
        self._models_error = self.controller.models_error or ""
        self._fallback_error = self.controller.fallback_models_error or ""
        self._refresh_model_list()
        self._refresh_fallback_models()
        self._sync_connect_status()
        self._sync_fallback_status()
        self._update_about()

    def _save(self) -> None:
        settings = self.controller.settings
        provider = self._current_provider(self.provider_combo, settings.provider)
        settings.provider = provider
        settings.base_url = self.base_url_edit.text().strip()
        settings.model = self.model_edit.text().strip()
        settings.api_key = self.api_key_field.value()

        fallback_provider = self._current_provider(
            self.fallback_provider_combo, settings.fallback_provider
        )
        settings.fallback_enabled = self.fallback_toggle.is_checked()
        settings.fallback_provider = fallback_provider
        settings.fallback_base_url = self.fallback_base_edit.text().strip()
        settings.fallback_model = self.fallback_model_combo.currentText().strip()
        settings.fallback_api_key = self.fallback_key_field.value()

        settings.temperature = self.temperature_field.value()
        settings.top_p = self.top_p_field.value()
        settings.top_k = int(round(self.top_k_field.value()))
        settings.repetition_penalty = self.repetition_field.value()
        settings.context_window = int(round(self.context_field.value()))

        settings.auto_translate = self.auto_toggle.is_checked()
        settings.translate_in_one_request = self.translate_in_one_request_toggle.is_checked()
        settings.debounce = self.debounce_field.value()
        settings.keep_history = self.keep_history_toggle.is_checked()
        settings.warm_up_on_launch = self.warm_up_toggle.is_checked()
        settings.show_in_menu_bar = self.tray_toggle.is_checked()
        settings.speech_voice_id = str(self.voice_combo.currentData() or "")

        translated_hotkey = self._combo_from_edit(self.hotkey_edit)
        if translated_hotkey is not None and translated_hotkey.is_valid:
            settings.hot_key = translated_hotkey
        selection_hotkey = self._combo_from_edit(self.selection_hotkey_edit)
        if selection_hotkey is not None and selection_hotkey.is_valid:
            settings.selection_hot_key = selection_hotkey

        self.controller.save_settings()

        language = self._current_language(self.language_combo)
        self.controller.set_interface_language(language)

        style = TranslationStyle(self.style_chips.value())
        tone = TranslationTone(self.tone_chips.value())
        target_code = self.target_combo.code() or self.controller.target_language.code
        if style != self.controller.style:
            self.controller.set_style(style)
        if tone != self.controller.tone:
            self.controller.set_tone(tone)
        if target_code != self.controller.target_language.code:
            self.controller.set_target_language(target_code)

        self.accept()

    def _restore_initial(self) -> None:
        if not self._initial:
            return
        self._connect_hint_provider = None
        values = self._initial
        settings = self.controller.settings
        settings.provider = values["provider"]
        settings.base_url = values["base_url"]
        settings.model = values["model"]
        settings.api_key = values["api_key"]
        settings.fallback_enabled = values["fallback_enabled"]
        settings.fallback_provider = values["fallback_provider"]
        settings.fallback_base_url = values["fallback_base_url"]
        settings.fallback_model = values["fallback_model"]
        settings.fallback_api_key = values["fallback_api_key"]
        settings.temperature = values["temperature"]
        settings.top_p = values["top_p"]
        settings.top_k = values["top_k"]
        settings.repetition_penalty = values["repetition_penalty"]
        settings.context_window = values["context_window"]
        settings.auto_translate = values["auto_translate"]
        settings.translate_in_one_request = values["translate_in_one_request"]
        settings.debounce = values["debounce"]
        settings.keep_history = values["keep_history"]
        settings.warm_up_on_launch = values["warm_up_on_launch"]
        settings.show_in_menu_bar = values.get("show_in_menu_bar", True)
        settings.interface_language = values["interface_language"]
        settings.speech_voice_id = values.get("speech_voice_id", "")
        settings.hot_key = values["hot_key"]
        settings.selection_hot_key = values["selection_hot_key"]
        settings.save()
        self._load_from_settings(capture=False)

    # -------------------------------------------------------------- events
    def reject(self) -> None:  # noqa: D401 - QDialog API
        self._restore_initial()
        super().reject()

    def showEvent(self, event: object) -> None:  # noqa: N802
        if self._shown_once:
            self._load_from_settings(capture=True)
        else:
            self._shown_once = True
        self._refresh_open_at_login()
        self._apply_theme()
        super().showEvent(event)

    # ------------------------------------------------------------ provider
    @staticmethod
    def _fill_provider_combo(combo: QComboBox, provider: Provider) -> None:
        combo.clear()
        for item in Provider:
            combo.addItem(t(item.title), item.value)
        index = combo.findData(provider.value)
        combo.setCurrentIndex(max(0, index))

    @staticmethod
    def _current_provider(combo: QComboBox, fallback: Provider) -> Provider:
        value = combo.currentData()
        if isinstance(value, Provider):
            return value
        if isinstance(value, str):
            found = Provider.from_stored(value)
            if found is not None:
                return found
        return fallback

    @staticmethod
    def _fill_language_combo(combo: QComboBox, language: AppLanguage) -> None:
        combo.clear()
        for item in AppLanguage:
            combo.addItem(item.picker_title, item.value)
        index = combo.findData(language.value)
        combo.setCurrentIndex(max(0, index))

    @staticmethod
    def _current_language(combo: QComboBox) -> AppLanguage:
        value = combo.currentData()
        if isinstance(value, AppLanguage):
            return value
        if isinstance(value, str):
            try:
                return AppLanguage(value)
            except ValueError:
                pass
        return AppLanguage.SYSTEM

    def _sync_provider_widgets(self, provider: Provider) -> None:
        self.provider_detail.setText(t(provider.detail_key))
        self.api_key_field.set_provider(provider)
        if provider.requires_key:
            hint = t("Required for this provider. Stored securely on this computer.")
        else:
            hint = t("Can be empty for local servers. Stored securely on this computer.")
        self.api_key_fill.set_hint(hint)

    def _sync_fallback_provider_widgets(self, provider: Provider) -> None:
        self.fallback_key_field.set_provider(provider)
        if provider.requires_key:
            hint = t("Uses the stored key for this provider.")
        else:
            hint = t("Can be empty for local servers. Stored securely on this computer.")
        self.fallback_key_row.set_hint(hint)

    def _stored_key(self, provider: Provider) -> str:
        """Read a provider's saved key without changing the live settings."""
        try:
            store = self.controller.settings._secret_store()
            if store is None:
                return ""
            return str(store.read(provider.key_account) or "")
        except Exception:  # noqa: BLE001 - a broken keyring must not break the UI
            return ""

    def _on_primary_provider_changed(self, _index: int) -> None:
        provider = self._current_provider(
            self.provider_combo, self.controller.settings.provider
        )
        self.base_url_edit.setText(provider.base_url)
        origin = self._initial.get("provider")
        if provider == origin:
            self.model_edit.setText(self._initial.get("model", ""))
            self.api_key_field.set_value(self._initial.get("api_key", ""))
        else:
            self.model_edit.clear()
            self.api_key_field.set_value(self._stored_key(provider))
        self._connect_hint_provider = None
        self._sync_provider_widgets(provider)
        self._models_cache = []
        self._models_error = ""
        self._refresh_model_list()
        self._sync_connect_status()

    def _on_fallback_provider_changed(self, _index: int) -> None:
        provider = self._current_provider(
            self.fallback_provider_combo, self.controller.settings.fallback_provider
        )
        self.fallback_base_edit.setText(provider.base_url)
        origin = self._initial.get("fallback_provider")
        if provider == origin:
            self.fallback_model_combo.setEditText(
                self._initial.get("fallback_model", "")
            )
            self.fallback_key_field.set_value(
                self._initial.get("fallback_api_key", "")
            )
        else:
            self.fallback_model_combo.setEditText("")
            self.fallback_key_field.set_value(self._stored_key(provider))
        self._sync_fallback_provider_widgets(provider)
        self._fallback_models_cache = []
        self._fallback_error = ""
        self._refresh_fallback_models()

    # --------------------------------------------------------------- models
    def _connect_models(self) -> None:
        self._stage_primary_settings()
        provider = self._current_provider(
            self.provider_combo, self.controller.settings.provider
        )
        if provider.requires_key and not self.api_key_field.value():
            self._connect_hint_provider = provider
            self._sync_connect_status()
            self._update_install_command()
            return
        self._connect_hint_provider = None
        self._models_error = ""
        self._sync_connect_status()
        self.controller.connect_and_load_models()

    def _refresh_models(self) -> None:
        """Re-run the probe with the provider values currently shown."""
        if self._models_loading:
            return
        self._stage_primary_settings()
        self._connect_hint_provider = None
        self._models_error = ""
        self._sync_connect_status()
        self.controller.connect_and_load_models()

    def _stage_primary_settings(self) -> None:
        settings = self.controller.settings
        settings.provider = self._current_provider(
            self.provider_combo, settings.provider
        )
        settings.base_url = self.base_url_edit.text().strip()
        settings.model = self.model_edit.text().strip()
        settings.api_key = self.api_key_field.value()

    def _stage_fallback_settings(self) -> None:
        settings = self.controller.settings
        settings.fallback_provider = self._current_provider(
            self.fallback_provider_combo, settings.fallback_provider
        )
        settings.fallback_base_url = self.fallback_base_edit.text().strip()
        settings.fallback_model = self.fallback_model_combo.currentText().strip()
        settings.fallback_api_key = self.fallback_key_field.value()

    def _on_models_changed(self, models: object) -> None:
        self._models_cache = sorted(
            [str(model) for model in (models or [])], key=str.casefold
        )
        self._models_error = ""
        self._refresh_model_list()

    def _on_models_loading(self, loading: bool) -> None:
        self._models_loading = bool(loading)
        self._connect_button_state()
        self._refresh_model_list()
        self._sync_connect_status()

    def _on_models_error(self, message: str) -> None:
        self._models_error = str(message or "")
        self._refresh_model_list()
        self._sync_connect_status()

    def _connect_button_state(self) -> None:
        self.connect_button.setEnabled(not self._models_loading)
        self.models_refresh.setEnabled(not self._models_loading)

    def _refresh_model_list(self) -> None:
        needle = (self.model_filter.text() or "").strip().casefold()
        matches = [
            model for model in self._models_cache if not needle or needle in model.casefold()
        ]

        self.models_list.setUpdatesEnabled(False)
        try:
            self.models_list.clear()
            current = self.model_edit.text().strip()
            for model in matches:
                item = QListWidgetItem(model)
                item.setData(Qt.ItemDataRole.UserRole, model)
                if model == current:
                    item.setIcon(icons.icon("check", Theme.palette().accent, 13))
                self.models_list.addItem(item)
        finally:
            self.models_list.setUpdatesEnabled(True)

        has_models = bool(self._models_cache)
        self.model_filter.setVisible(has_models)
        self.models_list.setVisible(has_models)
        self.models_count_label.setText(
            tf("Models: %d", len(self._models_cache)) if has_models else ""
        )

        if self._models_loading:
            self.models_hint.setText(t("Checking connection…"))
            self.models_hint.setVisible(True)
        elif self._models_error:
            self.models_hint.setText(t("Select a model from the list or type its ID."))
            self.models_hint.setVisible(True)
        elif has_models:
            self.models_hint.setText(t("Select a model from the list or type its ID."))
            self.models_hint.setVisible(False)
        else:
            self.models_hint.setText(t("Connect to load the model list."))
            self.models_hint.setVisible(True)

        self.models_error_label.setText(self._models_error)
        self.models_error_label.setVisible(bool(self._models_error))
        self._connect_button_state()
        self._update_install_command()

    def _on_model_clicked(self, item: QListWidgetItem) -> None:
        model = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
        self.model_edit.setText(model)

    def _on_model_text_changed(self, _text: str) -> None:
        current = self.model_edit.text().strip()
        self.models_list.setUpdatesEnabled(False)
        try:
            for index in range(self.models_list.count()):
                item = self.models_list.item(index)
                selected = str(item.data(Qt.ItemDataRole.UserRole)) == current
                item.setIcon(
                    icons.icon("check", Theme.palette().accent, 13)
                    if selected
                    else QIcon()
                )
                if selected:
                    self.models_list.setCurrentItem(item)
        finally:
            self.models_list.setUpdatesEnabled(True)
        self._update_install_command()

    def _connect_hint(self) -> str:
        provider = self._connect_hint_provider
        if provider is None:
            return ""
        return tf("Enter the API key for %@ in Settings first.", t(provider.title))

    def _sync_connect_status(self) -> None:
        hint = self._connect_hint()
        status = self.controller.backend_status
        message = self.controller.probe_message
        if hint:
            text, role = hint, "danger"
        elif self._models_loading:
            text, role = t("Connecting…"), "warning"
        elif status == "connected":
            text, role = (message or t("Connected")), "success"
        elif status == "failed":
            text, role = (message or t("Server unavailable")), "danger"
        elif status in ("checking", "warming"):
            text, role = (message or t("Checking connection…")), "warning"
        else:
            text, role = t("Not checked yet"), "muted"
        self.connect_status.setText(text)
        self.connect_status.set_role(role)

    def _probe_reported_missing_model(self) -> bool:
        """True when the last probe failed because the chosen model is absent."""
        model = self.model_edit.text().strip()
        if not model:
            return False
        message = (self._models_error or self.controller.models_error or "").strip()
        if not message:
            return False
        lowered = message.casefold()
        if "missing" in lowered or "not found" in lowered:
            return True
        if message == tf("Model “%@” not found", model):
            return True
        template = t("Server responds, but model “%@” is missing. Available: %@.")
        before, placeholder, remainder = template.partition("%@")
        after_model, second, _tail = remainder.partition("%@")
        if placeholder and second and after_model:
            if message.startswith(before) and after_model in message[len(before):]:
                return True
        listed = {item.casefold() for item in self._models_cache}
        return bool(listed) and model.casefold() not in listed

    def _update_install_command(self) -> None:
        command = ""
        if not self._models_loading and self._probe_reported_missing_model():
            command = self.controller.settings.install_command() or ""
        self.install_row.set_command(command)
        self.install_row.setVisible(bool(command))

    # ------------------------------------------------------------- fallback
    def _sync_fallback_body(self) -> None:
        self.fallback_body.setVisible(self.fallback_toggle.is_checked())

    def _load_fallback_models(self) -> None:
        self._stage_fallback_settings()
        self._fallback_error = ""
        self._sync_fallback_status()
        self.controller.load_fallback_models()

    def _on_fallback_models_changed(self, models: object) -> None:
        self._fallback_models_cache = sorted(
            [str(model) for model in (models or [])], key=str.casefold
        )
        self._fallback_error = ""
        self._refresh_fallback_models()

    def _on_fallback_loading(self, loading: bool) -> None:
        self._fallback_loading = bool(loading)
        self.load_fallback_button.setEnabled(not self._fallback_loading)
        self._refresh_fallback_models()
        self._sync_fallback_status()

    def _on_fallback_error(self, message: str) -> None:
        self._fallback_error = str(message or "")
        self._refresh_fallback_models()
        self._sync_fallback_status()

    def _refresh_fallback_models(self) -> None:
        current = self.fallback_model_combo.currentText().strip()
        with QSignalBlocker(self.fallback_model_combo):
            self.fallback_model_combo.clear()
            for model in self._fallback_models_cache:
                self.fallback_model_combo.addItem(model)
            self.fallback_model_combo.setEditText(current)
        self._sync_fallback_status()

    def _sync_fallback_status(self) -> None:
        if self._fallback_loading:
            text, role = t("Checking connection…"), "warning"
        elif self._fallback_error:
            text, role = self._fallback_error, "danger"
        elif self._fallback_models_cache:
            text, role = tf("Models: %d", len(self._fallback_models_cache)), "muted"
        else:
            text, role = "", "muted"
        self.fallback_status.setText(text)
        self.fallback_status.set_role(role)

    # -------------------------------------------------------------- preview
    def _update_preview(self) -> None:
        try:
            style = TranslationStyle(self.style_chips.value())
            tone = TranslationTone(self.tone_chips.value())
        except ValueError:  # pragma: no cover - chips only expose valid values
            style, tone = TranslationStyle.AUTO, TranslationTone.STANDARD
        target = get_language(self.target_combo.code()) or self.controller.target_language
        self.prompt_preview.setPlainText(
            PromptBuilder.preview(
                style, tone, target.english_name, sample=t("Sample text")
            )
        )

    # --------------------------------------------------------------- hotkey
    @staticmethod
    def _combo_from_text(text: str) -> KeyCombo | None:
        text = (text or "").strip()
        if not text:
            return None
        if text.endswith("++"):
            key = "+"
            modifiers = text[:-2].split("+")
        else:
            pieces = text.split("+")
            key = pieces[-1]
            modifiers = pieces[:-1]
        command = option = shift = False
        for modifier in modifiers:
            lowered = modifier.strip().lower()
            if lowered in ("ctrl", "control"):
                command = True
            elif lowered in ("alt", "option"):
                option = True
            elif lowered == "shift":
                shift = True
        if not key:
            return None
        return KeyCombo(key=key, command=command, option=option, shift=shift)

    @classmethod
    def _combo_from_edit(cls, edit: QKeySequenceEdit) -> KeyCombo | None:
        sequence = edit.keySequence()
        if sequence.isEmpty():
            return None
        text = sequence.toString(QKeySequence.SequenceFormat.PortableText)
        first = text.split(",")[0].strip()
        return cls._combo_from_text(first)

    @staticmethod
    def _set_hotkey_edit(edit: QKeySequenceEdit, combo: KeyCombo) -> None:
        with QSignalBlocker(edit):
            edit.setKeySequence(QKeySequence(combo.qt_sequence))

    def _validate_hotkey(self, edit: QKeySequenceEdit, row: FormRow) -> bool:
        combo = self._combo_from_edit(edit)
        valid = combo is not None and combo.is_valid
        row.set_hint("" if valid else t(_INVALID_HOTKEY_HINT))
        return valid

    def _sync_hotkey_caption(self, edit: QKeySequenceEdit) -> None:
        """Show the recording prompt while focused, the captured combo after."""
        caption = (
            self.hotkey_caption
            if edit is self.hotkey_edit
            else self.selection_hotkey_caption
        )
        if edit.hasFocus():
            caption.setText(t("Press a combination…"))
            return
        combo = self._combo_from_edit(edit)
        caption.setText(combo.display if combo is not None else "")

    # --------------------------------------------------------------- catalog
    def _open_catalog(self) -> None:
        try:
            dialog = CatalogView(self.controller, self)
            dialog.exec()
        except Exception:  # noqa: BLE001 - a broken catalogue must not kill settings
            log.exception("model catalog failed")
            return
        self._load_from_settings(capture=False)

    # ---------------------------------------------------------------- about
    def _secret_backend_name(self) -> str:
        if self._secret_backend:
            return self._secret_backend
        try:
            from ..services.secrets import SecretStore

            self._secret_backend = SecretStore().backend_name()
        except Exception:  # noqa: BLE001 - diagnostics only
            self._secret_backend = "unavailable"
        return self._secret_backend

    def _update_about(self) -> None:
        self.settings_path_label.setText(str(AppSettings.default_path()))
        history_path = getattr(self.controller.history, "path", None)
        if history_path is None:
            try:
                from ..services.history import HistoryStore

                history_path = HistoryStore.default_path()
            except Exception:  # pragma: no cover - defensive
                history_path = ""
        self.history_path_label.setText(str(history_path))
        backend = self._secret_backend_name()
        if backend == "keyring":
            label = "keyring · " + t("Windows Credential Manager")
        elif backend == "dpapi":
            label = "dpapi · " + t("Windows user scope")
        elif backend == "plain":
            label = "plain · 0600"
        else:
            label = backend
        self.key_backend_label.setText(label)

    # ------------------------------------------------------------- toggles
    @staticmethod
    def _apply_toggle(toggle: ToggleRow, checked: bool) -> None:
        """Set a ToggleRow and force its switch to the final visual position.

        ``ToggleRow.set_checked`` intentionally blocks the animation signal, so
        the custom switch would otherwise keep painting its old state until the
        user touches it.
        """
        toggle.set_checked(bool(checked))
        switch = toggle.check_box()
        position = 1.0 if checked else 0.0
        if hasattr(switch, "_pos"):
            switch._pos = position
        switch.update()

    # ---------------------------------------------------------------- theme
    def _apply_theme(self, *_args: object) -> None:
        palette = Theme.palette()
        self.header.setStyleSheet(
            f"QWidget#settingsHeader {{ background: {palette.panel}; }}"
        )
        self.footer.setStyleSheet(
            f"QWidget#settingsFooter {{ background: {palette.panel}; }}"
        )
        self.setStyleSheet(f"QDialog#settingsView {{ background: {palette.bg}; }}")
        self.tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{ border: none; background: transparent; }}
            QTabWidget::tab-bar {{ left: 15px; }}
            QTabBar {{ background: transparent; }}
            QTabBar::tab {{
                background: transparent;
                color: {palette.muted};
                border: none;
                border-radius: 8px;
                padding: 7px 13px;
                margin: 5px 4px 3px 0px;
                font-size: 13px;
                font-weight: 500;
            }}
            QTabBar::tab:hover {{ background: {palette.card_hover}; color: {palette.text}; }}
            QTabBar::tab:selected {{
                background: {palette.accent_soft};
                color: {palette.accent_hover};
                font-weight: 600;
            }}
            """
        )
        self.prompt_preview.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background: {palette.card_hover};
                color: {palette.muted};
                border: 1px solid {palette.border};
                border-radius: 8px;
                padding: 7px 10px;
                font-family: "{Theme.mono_family()}";
                font-size: 10px;
            }}
            """
        )

    # ----------------------------------------------------------- translate
    def retranslate_ui(self) -> None:
        self.setWindowTitle(t("Settings"))
        self.title_label.setText(t("Settings"))
        self.version_label.setText(f"{APP_NAME} {__version__}")

        self.tabs.setTabText(0, t("Model & provider").replace("&", "&&"))
        self.tabs.setTabText(1, t("Generation"))
        self.tabs.setTabText(2, t("Behavior"))
        self.tabs.setTabText(3, t("Hot keys"))
        self.tabs.setTabText(4, t("About"))

        # --- model tab
        self.model_card.set_title(t("Model and provider"))
        self.model_card.set_subtitle(
            t(
                "Local models run offline and for free. Cloud models answer faster "
                "but need a key."
            )
        )
        self.provider_row.set_label(t("Provider"))
        self.provider_combo.setAccessibleName(t("Provider"))
        self.address_row.set_label(t("Server address"))
        self.api_key_fill.set_label(t("API key"))
        self.model_row.set_label(t("Model"))
        self.catalog_button.setText(t("Model catalog…"))
        self.connect_button.setText(t("Connect"))
        self.models_title_label.setText(t("Models on the server"))
        self.models_refresh.setText(t("Refresh"))
        self.models_refresh.setToolTip(t("Refresh"))
        self.install_row.retranslate_ui()
        self.model_filter.set_placeholder(t("Filter by name"))

        with QSignalBlocker(self.provider_combo):
            current = self._current_provider(
                self.provider_combo, self.controller.settings.provider
            )
            self._fill_provider_combo(self.provider_combo, current)
        self._sync_provider_widgets(current)
        self._sync_connect_status()
        self.api_key_field.retranslate_ui()
        self._refresh_model_list()

        # --- fallback card
        self.fallback_card.set_title(t("Fallback provider"))
        self.fallback_card.set_subtitle(
            t("Used automatically when the primary provider fails.")
        )
        self.fallback_toggle.set_label(t("Use a fallback provider"))
        self.fallback_provider_row.set_label(t("Provider"))
        self.fallback_provider_combo.setAccessibleName(t("Provider"))
        self.fallback_address_row.set_label(t("Server address"))
        self.fallback_key_row.set_label(t("API key"))
        self.fallback_model_row.set_label(t("Model"))
        self.fallback_model_combo.lineEdit().setPlaceholderText(t("Choose a model"))
        self.load_fallback_button.setText(t("Load models"))
        self.fallback_hint_label.setText(
            t("If the primary provider fails, the same text is retried with these settings.")
        )
        with QSignalBlocker(self.fallback_provider_combo):
            fallback_provider = self._current_provider(
                self.fallback_provider_combo, self.controller.settings.fallback_provider
            )
            self._fill_provider_combo(self.fallback_provider_combo, fallback_provider)
        self._sync_fallback_provider_widgets(fallback_provider)
        self.fallback_key_field.retranslate_ui()
        self._refresh_fallback_models()
        self._sync_fallback_status()

        # --- generation tab
        self.generation_card.set_title(t("Generation parameters"))
        self.generation_card.set_subtitle(
            t("Defaults match Tencent’s recommendations for Hy-MT2 7B.")
        )
        self.temperature_row.set_label(t("Temperature"))
        self.repetition_row.set_label(t("Repetition"))
        self.context_row.set_label(t("Context"))
        self.prompt_card.set_title(t("System prompt"))
        self.prompt_card.set_subtitle(
            t(
                "Hy-MT2 has no system prompt: instruction and text go in one "
                "message. Wording follows the model card."
            )
        )
        self.style_row.set_label(t("Style"))
        self.tone_row.set_label(t("Tone"))
        self.target_row.set_label(t("Translate to"))
        self.style_chips.retranslate_ui()
        self.tone_chips.retranslate_ui()
        self.target_combo.retranslate_ui()
        self._update_preview()

        # --- behaviour tab
        self.behaviour_card.set_title(t("Behavior"))
        self.auto_toggle.set_label(t("Translate automatically while typing"))
        self.debounce_row.set_label(t("Delay"))
        self.translate_in_one_request_toggle.set_label(t("Translate text in one request"))
        self.keep_history_toggle.set_label(t("Keep translation history"))
        self.login_toggle.set_label(t("Open at login"))
        self.login_hint.setText(
            t("Allow DeepL-oFM to open at login in System Settings.")
        )
        self.login_settings_button.setText(t("Open System Settings"))
        self.tray_toggle.set_label(t("Tray icon"))
        self.tray_toggle.set_hint(
            t("Keep DeepL-oFM in the notification area; closing the window then hides it.")
        )
        self.warm_up_toggle.set_label(t("Load the translator at launch"))
        self.warm_up_toggle.set_hint(
            t(
                "Connects to the provider, refreshes the model list and warms up "
                "a local model."
            )
        )
        self.language_row.set_label(t("Interface language"))
        self.language_combo.setAccessibleName(t("Interface language"))
        with QSignalBlocker(self.language_combo):
            current_language = self._current_language(self.language_combo)
            self._fill_language_combo(self.language_combo, current_language)

        # --- hot keys tab
        self.hotkey_card.set_title(t("Hot key"))
        self.hotkey_card.set_subtitle(
            t(
                "Copy text anywhere and press the shortcut — DeepL-oFM opens and "
                "translates the clipboard."
            )
        )
        self.hotkey_row.set_label(t("Translate clipboard"))
        self.selection_hotkey_row.set_label(t("Selected text"))
        self.hotkey_hint.setText(
            t(
                "Select text in any app and press the shortcut — DeepL-oFM copies "
                "it and translates."
            )
        )
        self.hotkey_examples.setText(t("Examples: Ctrl+Alt+T or Ctrl+Alt+C."))
        self._validate_hotkey(self.hotkey_edit, self.hotkey_row)
        self._validate_hotkey(self.selection_hotkey_edit, self.selection_hotkey_row)
        self._sync_hotkey_caption(self.hotkey_edit)
        self._sync_hotkey_caption(self.selection_hotkey_edit)

        # --- about tab
        self.about_card.set_title(t("About"))
        self.model_license.setText(
            t("Model: Hy-MT2 7B (Tencent Hy). License and model card on Hugging Face.")
        )
        self.about_description.setText(
            t("A native translator for local and cloud models.")
        )
        self.about_license.setText(t("MIT license · free and open source."))
        self.github_button.setText(t("DeepL-oFM on GitHub"))
        self.settings_row.set_label(t("Settings file"))
        self.history_row.set_label(t("History file"))
        self.key_row.set_label(t("Key storage"))
        self._update_about()

        # --- chrome
        self.footer_hint.setText(t("Changes apply when you save."))
        self.cancel_button.setText(t("Cancel"))
        self.save_button.setText(t("Save"))
        self._apply_theme()
