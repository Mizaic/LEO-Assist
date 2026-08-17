"""post_login_path -- generic homes vs deep links."""

from libs.auth.post_login import post_login_path


def test_platform_admin_generic_home_goes_to_knowledge() -> None:
    assert post_login_path("/care/dashboard", is_platform_admin=True) == (
        "/admin/knowledge"
    )
    assert post_login_path("/", is_platform_admin=True) == "/admin/knowledge"
    assert post_login_path("/dashboard", is_platform_admin=True) == (
        "/admin/knowledge"
    )


def test_platform_admin_keeps_a_deep_link() -> None:
    assert post_login_path("/admin/platform", is_platform_admin=True) == (
        "/admin/platform"
    )


def test_other_users_keep_care_home() -> None:
    assert post_login_path("/care/dashboard", is_platform_admin=False) == (
        "/care/dashboard"
    )
    assert post_login_path("/", is_platform_admin=False) == "/dashboard"
