"""Widget factory system for creating widgets in a type-safe and extensible manner."""

from typing import Any, Optional

from fabric.utils import logger


class IndexedWidgetHelper:
    """Indexed widget resolution shared by every collection type."""

    @staticmethod
    def validate_and_get_index(
        identifier: str, collection: list, collection_name: str
    ) -> Optional[int]:
        """Return the index *identifier* names in *collection*, or None.

        Digits are read as an index; anything else is matched against each
        item's ``id`` field.
        """
        if identifier.isdigit():
            index = int(identifier)
            if not isinstance(collection, list) or not (0 <= index < len(collection)):
                logger.warning(
                    f"{collection_name} index {index} out of range "
                    f"(0-{len(collection) - 1})"
                )
                return None
            return index

        try:
            for idx, item in enumerate(collection):
                if isinstance(item, dict) and item.get("id") == identifier:
                    return idx
        except (ValueError, TypeError):
            pass

        logger.warning(f"{collection_name}: no item with id '{identifier}' found")
        return None

    @staticmethod
    def get_config_path(config: dict, *path_parts: str) -> list:
        """Walk *path_parts* into *config*, or [] if the result is not a list."""
        result = config
        for part in path_parts:
            result = result.get(part, {})
        return result if isinstance(result, list) else []


class WidgetResolver:
    """Universal widget resolver with unified handling for all widget types."""

    def __init__(self, widgets_list: dict[str, type]):
        self.widgets_list = widgets_list
        self.helper = IndexedWidgetHelper()

    def resolve_widget(
        self, widget_spec: str, context: dict[str, Any]
    ) -> Optional[Any]:
        """Resolve any widget spec, logging and swallowing failures."""
        try:
            if widget_spec.startswith("@"):
                widget_type, identifier = self._parse_reference(widget_spec)
                return self._resolve_by_type(widget_type, identifier, context)
            else:
                return self._resolve_by_type("widget", widget_spec, context)

        except Exception:
            logger.exception(f"Failed to resolve widget '{widget_spec}'")
            return None

    def _parse_reference(self, widget_spec: str) -> tuple[str, str]:
        """Parse @type:identifier format."""
        parts = widget_spec[1:].split(":", 1)
        return parts[0], parts[1] if len(parts) > 1 else ""

    def _resolve_by_type(
        self, widget_type: str, identifier: str, context: dict[str, Any]
    ) -> Optional[Any]:
        """Dispatch to the builder registered for *widget_type*."""
        resolvers = {
            "widget": lambda: self._create_simple_widget(identifier, context),
            "group": lambda: self._create_indexed_widget(
                identifier,
                context,
                "widget_group",
                ["widget_groups"],
                self._instantiate_widget_group,
            ),
            "collapsible": lambda: self._create_indexed_widget(
                identifier,
                context,
                "collapsible_group",
                ["collapsible_groups"],
                self._instantiate_collapsible_group,
            ),
            "custom_widget": lambda: self._create_indexed_widget(
                identifier,
                context,
                "custom_widget",
                ["widgets", "custom_widget"],
                self._instantiate_custom_widget,
            ),
        }

        resolver = resolvers.get(widget_type)
        return resolver() if resolver else None

    def _create_simple_widget(
        self, widget_name: str, context: dict[str, Any]
    ) -> Optional[Any]:
        """Create a plain widget, or a named custom one for ``custom/`` specs."""
        if widget_name.startswith("custom/"):
            return self._create_named_custom_widget(widget_name, context)

        widget_class = self.widgets_list.get(widget_name)
        return widget_class() if widget_class else None

    def _create_named_custom_widget(
        self, widget_name: str, context: dict[str, Any]
    ) -> Optional[Any]:
        """Create custom widget from named alias like custom/hello-world."""
        config = context.get("config", {})
        module_config = self._get_named_custom_widget_config(config, widget_name)
        if module_config is None:
            logger.warning(f"Named custom widget '{widget_name}' not found in config")
            return None

        from widgets.custom_widget import CustomWidget

        safe_name = widget_name.replace("/", "_").replace(" ", "_")
        return CustomWidget(
            widget_name=f"custom_widget_{safe_name}",
            config=module_config,
        )

    @staticmethod
    def _get_named_custom_widget_config(
        config: dict, widget_name: str
    ) -> Optional[dict]:
        """Resolve config for custom/<name> from supported config shapes."""
        widgets_config = config.get("widgets", {})
        if not isinstance(widgets_config, dict):
            return None

        # Shape 1: widgets["custom/hello-world"] = {...}
        direct = widgets_config.get(widget_name)
        if isinstance(direct, dict):
            return direct

        custom_name = (
            widget_name.split("/", 1)[1] if "/" in widget_name else widget_name
        )
        custom_widget = widgets_config.get("custom_widget", {})

        # Shape 2: widgets.custom_widget["hello-world"] = {...}
        if isinstance(custom_widget, dict):
            named = custom_widget.get(custom_name) or custom_widget.get(widget_name)
            return named if isinstance(named, dict) else None

        # Shape 3 (compat): [[widgets.custom_widget]] with optional `name`
        if isinstance(custom_widget, list):
            for item in custom_widget:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if isinstance(name, str) and name in (custom_name, widget_name):
                    return item

        return None

    def _create_indexed_widget(
        self,
        identifier: str,
        context: dict[str, Any],
        widget_type: str,
        config_path: list,
        instantiator_func,
    ) -> Optional[Any]:
        """Resolve *identifier* under *config_path* and instantiate it."""

        config = context.get("config", {})

        collection = self.helper.get_config_path(config, *config_path)

        index = self.helper.validate_and_get_index(identifier, collection, widget_type)
        if index is None:
            return None

        return instantiator_func(collection[index], config, index)

    def _instantiate_widget_group(
        self, group_config: dict, config: dict, index: int
    ) -> Any:
        """Create WidgetGroup instance."""
        from shared.widget_container import WidgetGroup

        return WidgetGroup.from_config(
            group_config,
            self.widgets_list,
            main_config=config,
        )

    def _instantiate_collapsible_group(
        self, group_config: dict, config: dict, index: int
    ) -> Any:
        """Create CollapsibleGroupWidget instance."""
        from shared.collapsible_group import CollapsibleGroupWidget

        collapsible_group = CollapsibleGroupWidget()
        collapsible_group.update_config(group_config)
        collapsible_group.widgets_config = group_config.get("widgets", [])
        collapsible_group.set_context(config, self.widgets_list)
        return collapsible_group

    def _instantiate_custom_widget(
        self, module_config: dict, config: dict, index: int
    ) -> Any:
        """Create CustomWidget instance."""
        from widgets.custom_widget import CustomWidget

        return CustomWidget(
            widget_name=f"custom_widget_{index}",
            config=module_config,
        )

    def batch_resolve(
        self, widget_specs: list[str], context: dict[str, Any]
    ) -> list[Any]:
        """Resolve multiple widgets efficiently."""
        return [
            widget
            for spec in widget_specs
            if (widget := self.resolve_widget(spec, context))
        ]
