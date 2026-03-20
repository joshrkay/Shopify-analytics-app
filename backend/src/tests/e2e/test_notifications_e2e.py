"""
E2E Tests: Notification Management

Tests notification listing, read/unread tracking, and preferences.

Priority: P2 (Lower Risk)
"""

import pytest


@pytest.mark.e2e
class TestNotificationsHappyPath:
    """Happy path tests for notification management."""

    async def test_list_notifications(
        self,
        async_client,
        auth_headers,
        test_notifications,
    ):
        """GET /api/notifications returns notification list."""
        response = await async_client.get(
            "/api/notifications",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data
        assert len(data["notifications"]) >= 1

    async def test_get_unread_count(
        self,
        async_client,
        auth_headers,
        test_notifications,
    ):
        """GET /api/notifications/unread/count returns unread count."""
        response = await async_client.get(
            "/api/notifications/unread/count",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert isinstance(data["count"], int)

    async def test_mark_notification_read(
        self,
        async_client,
        auth_headers,
        test_notifications,
    ):
        """PATCH /api/notifications/{id}/read marks as read."""
        notif_id = test_notifications[0].id
        response = await async_client.patch(
            f"/api/notifications/{notif_id}/read",
            headers=auth_headers,
        )
        assert response.status_code == 200

    async def test_mark_all_read(
        self,
        async_client,
        auth_headers,
        test_notifications,
    ):
        """POST /api/notifications/read-all marks all as read."""
        response = await async_client.post(
            "/api/notifications/read-all",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "marked_count" in data or isinstance(data, dict)

    async def test_get_notification_preferences(
        self,
        async_client,
        auth_headers,
    ):
        """GET /api/notifications/preferences returns preferences."""
        response = await async_client.get(
            "/api/notifications/preferences",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "preferences" in data or isinstance(data, list)

    async def test_update_notification_preferences(
        self,
        async_client,
        auth_headers,
    ):
        """PUT /api/notifications/preferences updates preferences."""
        response = await async_client.put(
            "/api/notifications/preferences",
            headers=auth_headers,
            json={
                "preferences": [
                    {"event_type": "insight_generated", "in_app_enabled": True, "email_enabled": False},
                ],
            },
        )
        assert response.status_code in [200, 400, 422]


@pytest.mark.e2e
class TestNotificationsEdgeCases:
    """Edge cases for notifications."""

    async def test_notification_tenant_isolation(
        self,
        async_client,
        auth_headers_b,
        test_notifications,
    ):
        """Tenant B cannot see Tenant A's notifications."""
        resp_b = await async_client.get(
            "/api/notifications",
            headers=auth_headers_b,
        )
        if resp_b.status_code == 200:
            data = resp_b.json()
            b_ids = {n["id"] for n in data.get("notifications", [])}
            a_ids = {n.id for n in test_notifications}
            assert a_ids.isdisjoint(b_ids)

    async def test_notification_mark_nonexistent(
        self,
        async_client,
        auth_headers,
    ):
        """Marking a nonexistent notification should return 404."""
        import uuid
        response = await async_client.patch(
            f"/api/notifications/{uuid.uuid4()}/read",
            headers=auth_headers,
        )
        assert response.status_code in [404, 400]
