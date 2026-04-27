"""Data access helpers for MCPServer plugin."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.core.lib.object import getObject, setLinkToObject
from app.core.models.Clasess import Class, Method, Object, Property
from app.database import session_scope

from .utils import parse_json_object


def set_class_template(class_name: str, template: str) -> Dict[str, Any]:
    with session_scope() as session:
        rec = session.query(Class).filter(Class.name == class_name).one_or_none()
        if rec is None:
            raise ValueError(f"Class not found: {class_name}")
        rec.template = template
        session.commit()
        return {
            "id": rec.id,
            "name": rec.name,
            "description": rec.description,
            "parent_id": rec.parent_id,
            "template": rec.template,
        }


def get_class_record(class_name: str) -> Optional[Dict[str, Any]]:
    with session_scope() as session:
        rec = session.query(Class).filter(Class.name == class_name).one_or_none()
        if rec is None:
            return None
        props = (
            session.query(Property)
            .filter(Property.class_id == rec.id)
            .order_by(Property.name)
            .all()
        )
        methods = (
            session.query(Method)
            .filter(Method.class_id == rec.id)
            .order_by(Method.name)
            .all()
        )
        method_map = {m.id: m.name for m in methods}
        return {
            "id": rec.id,
            "name": rec.name,
            "description": rec.description,
            "parent_id": rec.parent_id,
            "template": rec.template,
            "template_engine": "jinja2",
            "template_context_schema": {
                "roots": ["object"],
                "examples": [
                    "object.temp",
                    "object.pressure",
                    "object.status",
                ],
                "available_properties": [p.name for p in props],
            },
            "class_properties": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description or "",
                    "type": p.type or "",
                    "history": p.history,
                    "method_name": method_map.get(p.method_id),
                    "params": parse_json_object(p.params),
                }
                for p in props
            ],
            "class_methods": [
                {
                    "id": m.id,
                    "name": m.name,
                    "description": m.description or "",
                    "call_parent": m.call_parent,
                    "has_code": bool(m.code),
                    "exec_params": parse_json_object(getattr(m, "exec_params", None)),
                }
                for m in methods
            ],
        }


def default_object_template() -> str:
    return "<div><strong>{{ object.name }}</strong>{% if object.description %}: {{ object.description }}{% endif %}</div>"


def resolve_template_source(object_template: Any, class_template: Any) -> Tuple[str, str]:
    object_template_norm = str(object_template or "")
    class_template_norm = str(class_template or "")
    if object_template_norm.strip():
        return object_template_norm, "object"
    if class_template_norm.strip():
        return class_template_norm, "class"
    return default_object_template(), "default"


def get_object_record(object_name: str) -> Optional[Dict[str, Any]]:
    with session_scope() as session:
        obj = session.query(Object).filter(Object.name == object_name).one_or_none()
        if obj is None:
            return None
        cls = session.query(Class).filter(Class.id == obj.class_id).one_or_none() if obj.class_id else None
        template, source = resolve_template_source(obj.template, cls.template if cls else None)
        return {
            "id": obj.id,
            "name": obj.name,
            "description": obj.description or "",
            "class_id": obj.class_id,
            "class_name": cls.name if cls else None,
            "template": obj.template,
            "template_engine": "jinja2",
            "effective_template": template,
            "effective_template_source": source,
        }


def get_class_method_record(class_name: str, method_name: str) -> Optional[Dict[str, Any]]:
    with session_scope() as session:
        cls = session.query(Class).filter(Class.name == class_name).one_or_none()
        if cls is None:
            return None
        rec = (
            session.query(Method)
            .filter(Method.class_id == cls.id, Method.name == method_name)
            .one_or_none()
        )
        if rec is None:
            return None
        return {
            "id": rec.id,
            "description": rec.description,
            "code": rec.code,
            "call_parent": rec.call_parent,
        }


def get_class_property_record(class_name: str, property_name: str) -> Optional[Dict[str, Any]]:
    with session_scope() as session:
        cls = session.query(Class).filter(Class.name == class_name).one_or_none()
        if cls is None:
            return None
        rec = (
            session.query(Property)
            .filter(Property.class_id == cls.id, Property.name == property_name)
            .one_or_none()
        )
        if rec is None:
            return None
        return {
            "id": rec.id,
            "description": rec.description,
            "history": rec.history,
            "type": rec.type,
            "method_id": rec.method_id,
            "method_name": (
                session.query(Method).filter(Method.id == rec.method_id).with_entities(Method.name).scalar()
                if rec.method_id
                else None
            ),
            "params": parse_json_object(rec.params),
        }


def get_object_property_record(object_name: str, property_name: str) -> Optional[Dict[str, Any]]:
    with session_scope() as session:
        obj = session.query(Object).filter(Object.name == object_name).one_or_none()
        if obj is None:
            return None
        rec = (
            session.query(Property)
            .filter(Property.object_id == obj.id, Property.name == property_name)
            .one_or_none()
        )
        if rec is None:
            return None
        method_name = (
            session.query(Method).filter(Method.id == rec.method_id).with_entities(Method.name).scalar()
            if rec.method_id
            else None
        )
        return {
            "id": rec.id,
            "description": rec.description,
            "history": rec.history,
            "type": rec.type,
            "method_id": rec.method_id,
            "method_name": method_name,
            "params": parse_json_object(rec.params),
        }


def get_inherited_class_method_for_object(object_name: str, method_name: str) -> Optional[Dict[str, Any]]:
    with session_scope() as session:
        obj = session.query(Object).filter(Object.name == object_name).one_or_none()
        if obj is None or not obj.class_id:
            return None
        rec = (
            session.query(Method)
            .filter(Method.class_id == obj.class_id, Method.name == method_name)
            .one_or_none()
        )
        if rec is None:
            return None
        cls_name = session.query(Class).filter(Class.id == obj.class_id).with_entities(Class.name).scalar()
        return {
            "id": rec.id,
            "class_name": cls_name,
            "description": rec.description,
            "code": rec.code,
            "call_parent": rec.call_parent,
        }


def get_class_full_record(class_name: str) -> Optional[Dict[str, Any]]:
    with session_scope() as session:
        cls = session.query(Class).filter(Class.name == class_name).one_or_none()
        if cls is None:
            return None

        chain: List[Class] = []
        cur = cls
        while cur is not None:
            chain.append(cur)
            if cur.parent_id is None:
                break
            cur = session.query(Class).filter(Class.id == cur.parent_id).one_or_none()

        chain.reverse()
        own_props = (
            session.query(Property)
            .filter(Property.class_id == cls.id)
            .order_by(Property.name)
            .all()
        )
        own_methods = (
            session.query(Method)
            .filter(Method.class_id == cls.id)
            .order_by(Method.name)
            .all()
        )

        inherited_props_map: Dict[str, Dict[str, Any]] = {}
        inherited_methods_map: Dict[str, Dict[str, Any]] = {}
        own_prop_names = {p.name for p in own_props}
        own_method_names = {m.name for m in own_methods}

        for node in chain[:-1]:
            props = session.query(Property).filter(Property.class_id == node.id).all()
            methods = session.query(Method).filter(Method.class_id == node.id).all()
            method_names_by_id = {m.id: m.name for m in methods}
            for prop in props:
                if prop.name in own_prop_names or prop.name in inherited_props_map:
                    continue
                inherited_props_map[prop.name] = {
                    "name": prop.name,
                    "description": prop.description or "",
                    "type": prop.type or "",
                    "history": prop.history,
                    "method_name": method_names_by_id.get(prop.method_id),
                    "params": parse_json_object(prop.params),
                    "source_class": node.name,
                }
            for method in methods:
                if method.name in own_method_names or method.name in inherited_methods_map:
                    continue
                inherited_methods_map[method.name] = {
                    "name": method.name,
                    "description": method.description or "",
                    "call_parent": method.call_parent,
                    "has_code": bool(method.code),
                    "source_class": node.name,
                }

        own_method_names_by_id = {m.id: m.name for m in own_methods}
        return {
            "id": cls.id,
            "name": cls.name,
            "description": cls.description or "",
            "parent_id": cls.parent_id,
            "inheritance_chain": [node.name for node in chain],
            "template": cls.template,
            "template_engine": "jinja2",
            "own_properties": [
                {
                    "name": prop.name,
                    "description": prop.description or "",
                    "type": prop.type or "",
                    "history": prop.history,
                    "method_name": own_method_names_by_id.get(prop.method_id),
                    "params": parse_json_object(prop.params),
                }
                for prop in own_props
            ],
            "inherited_properties": list(inherited_props_map.values()),
            "own_methods": [
                {
                    "name": method.name,
                    "description": method.description or "",
                    "call_parent": method.call_parent,
                    "has_code": bool(method.code),
                }
                for method in own_methods
            ],
            "inherited_methods": list(inherited_methods_map.values()),
        }


def get_object_method_record(object_name: str, method_name: str) -> Optional[Dict[str, Any]]:
    with session_scope() as session:
        obj = session.query(Object).filter(Object.name == object_name).one_or_none()
        if obj is None:
            return None
        rec = (
            session.query(Method)
            .filter(Method.object_id == obj.id, Method.name == method_name)
            .one_or_none()
        )
        if rec is None:
            return None
        return {
            "id": rec.id,
            "description": rec.description,
            "code": rec.code,
            "call_parent": rec.call_parent,
        }


def get_property_links(object_name: str, property_name: str) -> List[str]:
    obj = getObject(object_name)
    if not obj:
        return []
    prop = getattr(obj, "properties", {}).get(property_name)
    if prop is None:
        return []
    links = getattr(prop, "linked", None) or []
    return [str(item) for item in links if item]


def restore_property_links(object_name: str, property_name: str, links_before: List[str]) -> None:
    if not links_before:
        return
    links_after = set(get_property_links(object_name, property_name))
    for link in links_before:
        if link not in links_after:
            setLinkToObject(object_name, property_name, link)
