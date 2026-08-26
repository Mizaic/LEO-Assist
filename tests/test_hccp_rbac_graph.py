"""HCCP RBAC graph contract -- LEO must match HCCP, never the reverse.

VT for the shared identity graph:

    (:User)-[:IS_MEMBER_OF]->(:Group)-[:HAS_ROLE]->(:Role)

A person who is also a clinician keeps the :Practitioner label on the
same node. Clinical queries stay on :Practitioner. RBAC queries use :User.
"""

from __future__ import annotations

from libs.cypher import admin_queries as aq
from libs.cypher import entra_group_queries as eg
from libs.cypher import role_queries as rq
from libs.cypher import schema_constraints as sc


def test_create_identity_node_is_user_and_practitioner():
    assert ":User" in aq.CREATE_PRACTITIONER
    assert ":Practitioner" in aq.CREATE_PRACTITIONER


def test_role_state_reads_user_via_group_membership():
    query = rq.GET_PRACTITIONER_ROLE_STATE
    assert ":User" in query
    assert "IS_MEMBER_OF" in query
    assert "HAS_ROLE" in query
    assert "[:HAS_ROLE]->(role:Role)" not in query.replace(
        "(g:Group)-[:HAS_ROLE]->(role:Role)", ""
    )


def test_entra_catalogue_binds_group_to_role_with_has_role():
    assert "GRANTS_ROLE" not in eg.RESOLVE_ROLES_FROM_ENTRA_GROUPS
    assert "[:HAS_ROLE]->" in eg.RESOLVE_ROLES_FROM_ENTRA_GROUPS
    assert "GRANTS_ROLE" not in eg.SEED_GROUP_BINDINGS
    assert "HAS_ROLE" in eg.SEED_GROUP_BINDINGS
    assert "GRANTS_ROLE" not in eg.LIST_ENTRA_GROUP_BINDINGS


def test_login_sync_writes_is_member_of_not_direct_user_role():
    assert "IS_MEMBER_OF" in eg.DROP_STALE_IS_MEMBER_OF
    assert "IS_MEMBER_OF" in eg.ADD_IS_MEMBER_OF
    assert ":User" in eg.DROP_STALE_IS_MEMBER_OF
    assert ":User" in eg.ADD_IS_MEMBER_OF
    assert "GRANTS_ROLE" not in eg.DROP_STALE_IS_MEMBER_OF
    assert "GRANTS_ROLE" not in eg.ADD_IS_MEMBER_OF


def test_admin_assign_role_goes_through_group_membership():
    assert "IS_MEMBER_OF" in aq.ASSIGN_USER_ROLE
    assert "(:Group)-[:HAS_ROLE]->" in aq.ASSIGN_USER_ROLE or (
        "(g:Group)-[:HAS_ROLE]->" in aq.ASSIGN_USER_ROLE
    )
    assert "IS_MEMBER_OF" in aq.REMOVE_USER_ROLE
    assert "IS_MEMBER_OF" in aq.LIST_USER_ROLES


def test_group_membership_queries_use_hccp_rel_and_user_label():
    assert "IS_MEMBER_OF" in aq.ADD_GROUP_MEMBER
    assert ":User" in aq.ADD_GROUP_MEMBER
    assert "IS_MEMBER_OF" in aq.REMOVE_GROUP_MEMBER
    assert "IS_MEMBER_OF" in aq.LIST_GROUP_MEMBERS
    assert "MEMBER_OF" not in aq.ADD_GROUP_MEMBER.replace("IS_MEMBER_OF", "")


def test_schema_has_user_constraint_and_email_index():
    joined = "\n".join(sc.PATIENT_SCHEMA_CONSTRAINTS)
    assert "FOR (u:User) REQUIRE u.id IS UNIQUE" in joined
    assert "FOR (u:User) ON (u.email)" in joined


def test_canonical_role_seed_sets_hccp_role_id():
    assert "r.id" in rq.SEED_CANONICAL_ROLES
