from neo4j import Transaction

from demisto_sdk.commands.content_graph.common import ContentTypes, Rel
from demisto_sdk.commands.content_graph.interface.neo4j.queries.common import run_query


NODE_PROPERTY_UNIQUENESS_TEMPLATE = 'CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE'
NODE_PROPERTY_EXISTENCE_TEMPLATE = 'CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS NOT NULL'
REL_PROPERTY_EXISTENCE_TEMPLATE = 'CREATE CONSTRAINT IF NOT EXISTS FOR ()-[r:{label}]-() REQUIRE r.{prop} IS NOT NULL'


def create_constraints(tx: Transaction) -> None:
    create_nodes_constraints(tx)
    # create_relationships_constraints(tx)


def create_nodes_constraints(tx: Transaction) -> None:
    create_node_property_uniqueness_constraint(tx, ContentTypes.COMMAND, 'id')
    create_node_property_uniqueness_constraint(tx, ContentTypes.COMMAND, 'node_id')


def create_node_property_uniqueness_constraint(
    tx: Transaction,
    content_type: ContentTypes,
    prop: str
) -> None:
    query = NODE_PROPERTY_UNIQUENESS_TEMPLATE.format(label=content_type, prop=prop)
    run_query(tx, query)


def create_node_property_existence_constraint(
    tx: Transaction,
    content_type: ContentTypes,
    prop: str,
) -> None:
    query = NODE_PROPERTY_EXISTENCE_TEMPLATE.format(label=content_type, prop=prop)
    run_query(tx, query)


def create_relationships_constraints(tx: Transaction) -> None:
    create_relationship_property_existence_constraint(tx, Rel.DEPENDS_ON, 'mandatorily')


def create_relationship_property_existence_constraint(
    tx: Transaction,
    rel: Rel,
    prop: str,
) -> None:
    query = REL_PROPERTY_EXISTENCE_TEMPLATE.format(label=rel, prop=prop)
    run_query(tx, query)