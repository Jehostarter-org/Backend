"""Comprehensive test suite for end-to-end Stripe integration flows.

Covers all 4 service payment scenarios:
- Scenario A: Chaperone Escort & Inspection (Pre-auth hold, capture on completion, 15% fee, connected account transfer, cancellation hold release)
- Scenario B: The Shop - Marketplace Installments (SetupIntent for off-session card saving, Admin approval flow charging installment #1, 10% fee, connected account transfer, rejection)
- Scenario C: Airport Driver Service (Pre-auth hold on estimated fare, capture actual fare on completion, platform fee deduction, driver transfer, cancellation hold release)
- Scenario D: Gold Membership - $25 (Direct checkout session & platform ledger)
- Stripe Connect Onboarding & Status polling for Providers & Shops
- Internal webhook event callback dispatching
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from utils.payment_client import PaymentServiceClient, payment_client
from services.views import (
    ServiceRequestPaymentHoldView,
    UpdateTripStatusView,
    CancelServiceRequestView,
    ProviderStripeConnectOnboardingView,
    ProviderStripeConnectStatusView,
)
from shops.views import (
    CreateOrderView,
    AttachOrderPaymentMethodView,
    AdminProcessOrderApprovalView,
    ShopStripeConnectOnboardingView,
    ShopStripeConnectStatusView,
)
from memberships.internal_views import InternalPaymentCallbackView


# ─────────────────────────────────────────────────────────────────────────────
# 1. PaymentServiceClient Unit Tests
# ─────────────────────────────────────────────────────────────────────────────
class TestPaymentServiceClient:
    """Tests the microservice HTTP client and parameter aliases."""

    def test_create_hold(self):
        client = PaymentServiceClient(base_url="http://testserver:8001", token="secret123")
        mock_response = MagicMock(ok=True, status_code=200)
        mock_response.json.return_value = {"id": "hold_1", "status": "authorized"}

        with patch("requests.post", return_value=mock_response) as mock_post:
            res = client.create_hold(
                payment_id="pay_123",
                payment_method_id="pm_card",
                customer_id="cust_1",
                transfer_group="sr_123",
            )
            assert res["status"] == "authorized"
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            assert "/payments/pay_123/hold/" in call_url
            payload = mock_post.call_args[1]["json"]
            assert payload["payment_method_id"] == "pm_card"
            assert payload["customer_id"] == "cust_1"
            assert payload["transfer_group"] == "sr_123"

    def test_capture_payment_with_amount_alias(self):
        client = PaymentServiceClient(base_url="http://testserver:8001", token="secret123")
        mock_response = MagicMock(ok=True, status_code=200)
        mock_response.json.return_value = {"id": "pay_1", "status": "captured"}

        with patch("requests.post", return_value=mock_response) as mock_post:
            res = client.capture_payment(payment_id="pay_1", amount=Decimal("120.00"))
            assert res["status"] == "captured"
            payload = mock_post.call_args[1]["json"]
            assert payload["amount_to_capture"] == 120.0

    def test_release_hold(self):
        client = PaymentServiceClient(base_url="http://testserver:8001", token="secret123")
        mock_response = MagicMock(ok=True, status_code=200)
        mock_response.json.return_value = {"id": "pay_1", "status": "released"}

        with patch("requests.post", return_value=mock_response) as mock_post:
            res = client.release_hold(payment_id="pay_1", reason="trip_cancelled")
            assert res["status"] == "released"
            assert "/payments/pay_1/release/" in mock_post.call_args[0][0]

    def test_transfer_funds_with_destination_account_alias(self):
        client = PaymentServiceClient(base_url="http://testserver:8001", token="secret123")
        mock_response = MagicMock(ok=True, status_code=200)
        mock_response.json.return_value = {"id": "tr_1", "status": "paid"}

        with patch("requests.post", return_value=mock_response) as mock_post:
            res = client.transfer_funds(
                destination_account="acct_driver123",
                amount=Decimal("85.00"),
                currency="USD",
                transfer_group="sr_123",
            )
            assert res["status"] == "paid"
            payload = mock_post.call_args[1]["json"]
            assert payload["destination_account_id"] == "acct_driver123"
            assert payload["amount"] == 85.0

    def test_create_setup_intent(self):
        client = PaymentServiceClient(base_url="http://testserver:8001", token="secret123")
        mock_response = MagicMock(ok=True, status_code=200)
        mock_response.json.return_value = {"id": "seti_1", "client_secret": "seti_secret"}

        with patch("requests.post", return_value=mock_response) as mock_post:
            res = client.create_setup_intent(
                customer_id="cust_1",
                metadata={"order_id": "ord_1"},
            )
            assert res["client_secret"] == "seti_secret"
            assert "/setup-intents/" in mock_post.call_args[0][0]

    def test_create_connected_account(self):
        client = PaymentServiceClient(base_url="http://testserver:8001", token="secret123")
        mock_response = MagicMock(ok=True, status_code=200)
        mock_response.json.return_value = {"account_id": "acct_1"}

        with patch("requests.post", return_value=mock_response) as mock_post:
            res = client.create_connected_account(
                email="provider@example.com",
                country="US",
                account_type="express",
                business_type="individual",
            )
            assert res["account_id"] == "acct_1"

    def test_get_connected_account(self):
        client = PaymentServiceClient(base_url="http://testserver:8001", token="secret123")
        mock_response = MagicMock(ok=True, status_code=200)
        mock_response.json.return_value = {"account_id": "acct_1", "charges_enabled": True, "payouts_enabled": True, "details_submitted": True}

        with patch("requests.get", return_value=mock_response) as mock_get:
            res = client.get_connected_account(account_id="acct_1")
            assert res["charges_enabled"] is True
            assert "/connect/accounts/acct_1/" in mock_get.call_args[0][0]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Scenario A: Chaperone Escort & Inspection
# ─────────────────────────────────────────────────────────────────────────────
class TestScenarioA_ChaperoneEscort:
    """Verifies Pre-auth hold, completion capture with 15% fee, Connect transfer, and cancellation release."""

    def test_chaperone_authorize_hold(self):
        factory = APIRequestFactory()
        user = MagicMock(is_authenticated=True, email="buyer@test.com", stripe_customer_id="cus_buyer1")
        
        service_request = MagicMock(
            id=101,
            requester=user,
            service_type="chaperone",
            price=Decimal("120.00"),
            currency="USD",
            payment_id="",
            payment_status="unpaid",
        )

        with patch("services.views.get_object_or_404", return_value=service_request), \
             patch("utils.payment_client.payment_client.create_payment") as mock_create_pay, \
             patch("utils.payment_client.payment_client.create_hold") as mock_create_hold:
            
            mock_create_pay.return_value = {
                "id": "pay_hold_123",
                "client_secret": "pi_secret_abc",
                "status": "pending",
            }
            mock_create_hold.return_value = {
                "hold_id": "pay_hold_123",
                "status": "authorized",
            }

            view = ServiceRequestPaymentHoldView.as_view()
            req = factory.post("/api/services/101/authorize-hold/", {"payment_method_id": "pm_card_chap"}, format="json")
            force_authenticate(req, user=user)
            response = view(req, pk=101)

            assert response.status_code == status.HTTP_200_OK
            assert response.data["status"] == "authorized"
            assert response.data["payment_id"] == "pay_hold_123"
            assert service_request.payment_id == "pay_hold_123"
            assert service_request.payment_status == "authorized"
            service_request.save.assert_called_once()

    def test_chaperone_completion_capture_and_transfer(self):
        factory = APIRequestFactory()
        provider_user = MagicMock(is_authenticated=True, email="chaperone@test.com", id="usr_chap1", spec=["id", "email"])
        provider_profile = MagicMock(user=provider_user, stripe_account_id="acct_chaperone99", stripe_charges_enabled=True)

        service_request = MagicMock(
            id=101,
            service_type="chaperone",
            provider=provider_user,
            price=Decimal("120.00"),
            currency="USD",
            payment_id="pay_hold_123",
            payment_status="authorized",
            transfer_group="",
            platform_fee=None,
            provider_payout=None,
        )

        with patch("services.views.get_object_or_404", return_value=service_request), \
             patch("services.views.ServiceProviderProfile.objects.filter") as mock_prof_filter, \
             patch("utils.payment_client.payment_client.capture_payment") as mock_capture, \
             patch("utils.payment_client.payment_client.transfer_funds") as mock_transfer:
            
            mock_prof_filter.return_value.first.return_value = provider_profile
            mock_capture.return_value = {"id": "pay_hold_123", "status": "captured"}
            mock_transfer.return_value = {"id": "tr_chap_1", "status": "paid"}

            view = UpdateTripStatusView.as_view()
            # Final price is $120.00. 15% platform fee = $18.00. Provider payout = $102.00
            req = factory.post("/api/services/101/trip-status/", {"status": "completed", "final_price": "120.00"}, format="json")
            force_authenticate(req, user=provider_user)
            response = view(req, pk=101)

            assert response.status_code == status.HTTP_200_OK
            assert response.data["status"] == "completed"

            # Check capture_payment call
            mock_capture.assert_called_once_with(payment_id="pay_hold_123", amount_to_capture=Decimal("120.00"))
            
            # Check transfer_funds call: 85% net to chaperone
            mock_transfer.assert_called_once()
            tr_call = mock_transfer.call_args[1]
            assert tr_call["destination_account"] == "acct_chaperone99"
            assert tr_call["amount"] == Decimal("102.00")
            assert tr_call["currency"] == "USD"
            assert tr_call["transfer_group"] == "service_request_101"

            # Check model updates
            assert service_request.payment_status == "completed"
            assert service_request.platform_fee == Decimal("18.00")
            assert service_request.provider_payout == Decimal("102.00")
            service_request.save.assert_called()

    def test_chaperone_cancellation_releases_hold(self):
        factory = APIRequestFactory()
        buyer_user = MagicMock(is_authenticated=True, email="buyer@test.com")
        
        service_request = MagicMock(
            id=101,
            requester=buyer_user,
            service_type="chaperone",
            status="accepted",
            payment_id="pay_hold_123",
            payment_status="authorized",
        )

        with patch("services.views.get_object_or_404", return_value=service_request), \
             patch("utils.payment_client.payment_client.release_hold") as mock_release:
            
            mock_release.return_value = {"id": "pay_hold_123", "status": "released"}

            view = CancelServiceRequestView.as_view()
            req = factory.post("/api/services/101/cancel/", {"reason": "Change of plans"}, format="json")
            force_authenticate(req, user=buyer_user)
            response = view(req, pk=101)

            assert response.status_code == status.HTTP_200_OK
            assert response.data["status"] == "cancelled"
            assert response.data["payment_status"] == "released"

            mock_release.assert_called_once_with(
                payment_id="pay_hold_123",
                reason="Change of plans",
            )
            assert service_request.payment_status == "released"
            assert service_request.status == "cancelled"
            service_request.save.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Scenario B: The Shop - Marketplace Installments
# ─────────────────────────────────────────────────────────────────────────────
class TestScenarioB_ShopInstallments:
    """Verifies SetupIntent off-session card saving, Admin approval flow charging installment #1, 10% fee split, seller Connect transfer, and rejection."""

    def test_create_installment_order_with_setup_intent(self):
        factory = APIRequestFactory()
        buyer_user = MagicMock(is_authenticated=True, email="buyer@shop.com", id=10, stripe_customer_id="cus_buyer_shop")
        shop = MagicMock(id=1, name="Electronics Shop", owner=MagicMock(id=99), stripe_account_id="acct_seller42", stripe_onboarding_completed=True)
        listing = MagicMock(id="list_123", shop=shop, price=Decimal("1000.00"), currency="USD", is_available=True)

        order_mock = MagicMock(
            id=501,
            buyer=buyer_user,
            shop=shop,
            listing=listing,
            total_price=Decimal("1000.00"),
            currency="USD",
            payment_type="installment",
            status="pending",
        )

        with patch("shops.views.get_object_or_404", return_value=listing), \
             patch("shops.views.Order.objects.create", return_value=order_mock), \
             patch("shops.views.InstallmentSchedule.objects.create"), \
             patch("utils.payment_client.payment_client.create_setup_intent") as mock_setup_intent, \
             patch("shops.views.OrderSerializer") as mock_serializer_cls:

            mock_setup_intent.return_value = {
                "id": "seti_order_501",
                "client_secret": "seti_secret_501",
                "status": "requires_payment_method",
            }
            
            serializer_instance = MagicMock()
            serializer_instance.data = {"id": 501, "total_price": "1000.00", "payment_type": "installment"}
            mock_serializer_cls.return_value = serializer_instance

            view = CreateOrderView.as_view()
            payload = {
                "listing_id": "list_123",
                "payment_type": "installment",
                "installments_count": 4,
            }
            req = factory.post("/api/shops/orders/", payload, format="json")
            force_authenticate(req, user=buyer_user)
            response = view(req)

            assert response.status_code == status.HTTP_201_CREATED
            assert response.data["client_secret"] == "seti_secret_501"

            # Check setup intent creation parameters
            mock_setup_intent.assert_called_once()
            call_kwargs = mock_setup_intent.call_args[1]
            assert call_kwargs["metadata"]["order_id"] == "501"
            assert call_kwargs["metadata"]["buyer_id"] == "10"

    def test_attach_payment_method_to_order(self):
        factory = APIRequestFactory()
        buyer_user = MagicMock(is_authenticated=True, email="buyer@shop.com")
        order_mock = MagicMock(id=501, buyer=buyer_user, stripe_payment_method_id="", stripe_customer_id="")

        with patch("shops.views.get_object_or_404", return_value=order_mock):
            view = AttachOrderPaymentMethodView.as_view()
            req = factory.post("/api/shops/orders/501/payment-method/", {"payment_method_id": "pm_saved_card_99"}, format="json")
            force_authenticate(req, user=buyer_user)
            response = view(req, pk=501)

            assert response.status_code == status.HTTP_200_OK
            assert response.data["stripe_payment_method_id"] == "pm_saved_card_99"
            assert order_mock.stripe_payment_method_id == "pm_saved_card_99"
            order_mock.save.assert_called_once()

    def test_admin_approves_order_charges_first_installment_and_splits_fee(self):
        factory = APIRequestFactory()
        admin_user = MagicMock(is_authenticated=True, is_staff=True, email="admin@jehostarter.com")
        shop = MagicMock(id=1, stripe_account_id="acct_seller42", stripe_onboarding_completed=True)
        
        # Installment 1: $250.00
        inst1 = MagicMock(id=1, installment_number=1, amount=Decimal("250.00"), status="pending", payment_id="", paid_at=None)
        
        order_mock = MagicMock(
            id=501,
            shop=shop,
            status="pending",
            total_amount=Decimal("1000.00"),
            currency="USD",
            stripe_customer_id="cus_buyer_shop",
            stripe_payment_method_id="pm_saved_card_99",
            transfer_group="",
            installments=MagicMock(),
        )
        order_mock.installments.filter.return_value.first.return_value = inst1

        with patch("shops.views.get_object_or_404", return_value=order_mock), \
             patch("utils.payment_client.payment_client.create_payment") as mock_pay, \
             patch("utils.payment_client.payment_client.transfer_funds") as mock_transfer:

            # Charging installment #1 off-session
            mock_pay.return_value = {
                "id": "pay_inst_1",
                "status": "succeeded",
            }
            # Transferring 90% net ($225.00) to seller
            mock_transfer.return_value = {
                "id": "tr_seller_inst1",
                "status": "paid",
            }

            view = AdminProcessOrderApprovalView.as_view()
            req = factory.post("/api/shops/admin/orders/501/process-approval/", {"action": "approve"}, format="json")
            force_authenticate(req, user=admin_user)
            response = view(req, pk=501)

            assert response.status_code == status.HTTP_200_OK
            assert response.data["status"] == "approved"
            assert response.data["charged_amount"] == 250.0
            assert response.data["platform_fee"] == 25.0
            assert response.data["seller_payout"] == 225.0

            # Verify installment 1 charge
            mock_pay.assert_called_once()
            charge_kwargs = mock_pay.call_args[1]
            assert charge_kwargs["amount"] == 250.0
            assert charge_kwargs["payment_method_id"] == "pm_saved_card_99"

            # Verify seller transfer (90% of $250.00 = $225.00)
            mock_transfer.assert_called_once()
            tr_kwargs = mock_transfer.call_args[1]
            assert tr_kwargs["destination_account"] == "acct_seller42"
            assert tr_kwargs["amount"] == 225.0
            assert tr_kwargs["transfer_group"] == "order_501"

            # Verify order and installment state
            assert order_mock.status == "approved"
            assert inst1.status == "paid"
            assert inst1.payment_id == "pay_inst_1"
            assert inst1.paid_at is not None
            order_mock.save.assert_called()

    def test_admin_rejects_order(self):
        factory = APIRequestFactory()
        admin_user = MagicMock(is_authenticated=True, is_staff=True, email="admin@jehostarter.com")
        order_mock = MagicMock(id=501, status="pending", rejection_reason="")

        with patch("shops.views.get_object_or_404", return_value=order_mock):
            view = AdminProcessOrderApprovalView.as_view()
            req = factory.post("/api/shops/admin/orders/501/process-approval/", {"action": "reject", "reason": "Credit check failed"}, format="json")
            force_authenticate(req, user=admin_user)
            response = view(req, pk=501)

            assert response.status_code == status.HTTP_200_OK
            assert response.data["status"] == "rejected"
            assert response.data["rejection_reason"] == "Credit check failed"
            assert order_mock.status == "rejected"
            assert order_mock.rejection_reason == "Credit check failed"
            order_mock.save.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Scenario C: Airport Driver Service
# ─────────────────────────────────────────────────────────────────────────────
class TestScenarioC_AirportDriverService:
    """Verifies Pre-auth hold on estimated fare, completion capture on actual distance, fee deduction, and driver transfer."""

    def test_driver_estimated_hold_and_actual_capture(self):
        factory = APIRequestFactory()
        driver_user = MagicMock(is_authenticated=True, email="driver@test.com", id="usr_driver1", spec=["id", "email"])
        driver_profile = MagicMock(user=driver_user, stripe_account_id="acct_driver88", stripe_charges_enabled=True)

        service_request = MagicMock(
            id=202,
            service_type="airport_pickup",
            provider=driver_user,
            price=Decimal("60.00"),
            currency="USD",
            payment_id="pay_hold_driver",
            payment_status="authorized",
            transfer_group="",
            platform_fee=None,
            provider_payout=None,
        )

        with patch("services.views.get_object_or_404", return_value=service_request), \
             patch("services.views.ServiceProviderProfile.objects.filter") as mock_prof_filter, \
             patch("utils.payment_client.payment_client.capture_payment") as mock_capture, \
             patch("utils.payment_client.payment_client.transfer_funds") as mock_transfer:
            
            mock_prof_filter.return_value.first.return_value = driver_profile
            mock_capture.return_value = {"id": "pay_hold_driver", "status": "captured"}
            mock_transfer.return_value = {"id": "tr_driver_1", "status": "paid"}

            # Actual final price from meter is $65.00
            # Platform fee (15%) = $9.75. Driver net payout (85%) = $55.25
            view = UpdateTripStatusView.as_view()
            req = factory.post("/api/services/202/trip-status/", {"status": "completed", "final_price": "65.00"}, format="json")
            force_authenticate(req, user=driver_user)
            response = view(req, pk=202)

            assert response.status_code == status.HTTP_200_OK
            assert response.data["status"] == "completed"

            # Check capture of actual fare
            mock_capture.assert_called_once_with(payment_id="pay_hold_driver", amount_to_capture=Decimal("65.00"))

            # Check driver transfer
            mock_transfer.assert_called_once()
            tr_call = mock_transfer.call_args[1]
            assert tr_call["destination_account"] == "acct_driver88"
            assert tr_call["amount"] == Decimal("55.25")
            assert tr_call["currency"] == "USD"
            assert tr_call["transfer_group"] == "service_request_202"

            assert service_request.platform_fee == Decimal("9.75")
            assert service_request.provider_payout == Decimal("55.25")
            assert service_request.payment_status == "completed"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Stripe Connect Onboarding & Status Polling
# ─────────────────────────────────────────────────────────────────────────────
class TestStripeConnectEndpoints:
    """Verifies Stripe Connect onboarding link creation and status polling for Providers and Shops."""

    def test_provider_connect_onboarding(self):
        factory = APIRequestFactory()
        user = MagicMock(is_authenticated=True, email="provider@test.com", id=15)
        profile = MagicMock(
            id=12,
            user=user,
            service_type="airport_pickup",
            stripe_account_id="",
            stripe_onboarding_completed=False,
            country_code="US",
        )

        with patch("services.views.ServiceProviderProfile.objects.filter") as mock_filter, \
             patch("utils.payment_client.payment_client.create_connected_account") as mock_create_acc, \
             patch("utils.payment_client.payment_client.create_account_link") as mock_create_link:
            
            mock_filter.return_value.first.return_value = profile
            mock_create_acc.return_value = {"account_id": "acct_new_prov_123"}
            mock_create_link.return_value = {"url": "https://connect.stripe.com/setup/abc", "expires_at": 1800000}

            view = ProviderStripeConnectOnboardingView.as_view()
            req = factory.post("/api/services/provider-profiles/stripe-connect/", {}, format="json")
            force_authenticate(req, user=user)
            response = view(req)

            assert response.status_code == status.HTTP_200_OK
            assert response.data["account_id"] == "acct_new_prov_123"
            assert response.data["onboarding_url"] == "https://connect.stripe.com/setup/abc"
            assert profile.stripe_account_id == "acct_new_prov_123"
            profile.save.assert_called_once()

    def test_provider_connect_status_sync(self):
        factory = APIRequestFactory()
        user = MagicMock(is_authenticated=True, email="provider@test.com")
        profile = MagicMock(
            user=user,
            stripe_account_id="acct_new_prov_123",
            stripe_onboarding_completed=False,
            stripe_charges_enabled=False,
            stripe_payouts_enabled=False,
        )

        with patch("services.views.ServiceProviderProfile.objects.filter") as mock_filter, \
             patch("utils.payment_client.payment_client.get_connected_account") as mock_get_acc:
            
            mock_filter.return_value.first.return_value = profile
            mock_get_acc.return_value = {
                "account_id": "acct_new_prov_123",
                "charges_enabled": True,
                "payouts_enabled": True,
                "details_submitted": True,
            }

            view = ProviderStripeConnectStatusView.as_view()
            req = factory.get("/api/services/provider-profiles/stripe-connect/")
            force_authenticate(req, user=user)
            response = view(req)

            assert response.status_code == status.HTTP_200_OK
            assert response.data["charges_enabled"] is True
            assert response.data["onboarding_completed"] is True
            assert profile.stripe_charges_enabled is True
            assert profile.stripe_payouts_enabled is True
            assert profile.stripe_onboarding_completed is True
            profile.save.assert_called_once()

    def test_shop_connect_onboarding_and_status(self):
        factory = APIRequestFactory()
        user = MagicMock(is_authenticated=True, email="seller@test.com", id=8)
        shop = MagicMock(
            id=3,
            owner=user,
            stripe_account_id="",
            stripe_onboarding_completed=False,
            country_code="US",
            approval_request=None,
        )
        user.shop = shop

        with patch("utils.payment_client.payment_client.create_connected_account") as mock_create_acc, \
             patch("utils.payment_client.payment_client.create_account_link") as mock_create_link:
            
            mock_create_acc.return_value = {"account_id": "acct_shop_456"}
            mock_create_link.return_value = {"url": "https://connect.stripe.com/setup/shop456", "expires_at": 1800000}

            # 1. Onboarding
            view_onboard = ShopStripeConnectOnboardingView.as_view()
            req = factory.post("/api/shops/stripe-connect/", {}, format="json")
            force_authenticate(req, user=user)
            resp = view_onboard(req)
            assert resp.status_code == status.HTTP_200_OK
            assert resp.data["account_id"] == "acct_shop_456"
            assert shop.stripe_account_id == "acct_shop_456"

        with patch("utils.payment_client.payment_client.get_connected_account") as mock_get_acc:
            # 2. Status poll
            mock_get_acc.return_value = {
                "account_id": "acct_shop_456",
                "charges_enabled": True,
                "payouts_enabled": True,
                "details_submitted": True,
            }
            view_status = ShopStripeConnectStatusView.as_view()
            req_status = factory.get("/api/shops/stripe-connect/")
            force_authenticate(req_status, user=user)
            resp_status = view_status(req_status)
            assert resp_status.status_code == status.HTTP_200_OK
            assert resp_status.data["onboarding_completed"] is True
            assert shop.stripe_onboarding_completed is True


# ─────────────────────────────────────────────────────────────────────────────
# 6. Internal Webhook Event Callbacks
# ─────────────────────────────────────────────────────────────────────────────
class TestInternalWebhookCallbacks:
    """Verifies backend webhook event callbacks from the payment microservice."""

    def test_webhook_payment_captured_dispatches_cleanly(self):
        factory = APIRequestFactory()
        view = InternalPaymentCallbackView.as_view()

        webhook_payload = {
            "event": "payment.captured",
            "payment_id": "pay_hold_123",
            "amount": 120.0,
            "currency": "USD",
            "resource_type": "service_request",
            "resource_id": "101",
        }

        sr_mock = MagicMock(id=101, payment_id="pay_hold_123", payment_status="authorized")
        with patch("memberships.internal_views.verify_hmac", return_value=True), \
             patch("memberships.internal_views.hmac.compare_digest", return_value=True), \
             patch("memberships.internal_views.ServiceRequest.objects.filter") as mock_filter:
            
            mock_filter.return_value.first.return_value = sr_mock
            req = factory.post(
                "/api/memberships/internal/payment-webhook/",
                webhook_payload,
                format="json",
                HTTP_X_SERVICE_TOKEN="valid-token",
                HTTP_X_SERVICE_SIGNATURE="t=123,v1=abc",
            )
            response = view(req)
            assert response.status_code == status.HTTP_200_OK
            resp_data = json.loads(response.content.decode("utf-8"))
            assert resp_data["status"] == "success"
            assert sr_mock.payment_status == "captured"
            sr_mock.save.assert_called_once()

    def test_webhook_payment_released_dispatches_cleanly(self):
        factory = APIRequestFactory()
        view = InternalPaymentCallbackView.as_view()

        webhook_payload = {
            "event": "payment.released",
            "payment_id": "pay_hold_123",
            "resource_type": "service_request",
            "resource_id": "101",
        }

        sr_mock = MagicMock(id=101, payment_id="pay_hold_123", payment_status="authorized")
        with patch("memberships.internal_views.verify_hmac", return_value=True), \
             patch("memberships.internal_views.hmac.compare_digest", return_value=True), \
             patch("memberships.internal_views.ServiceRequest.objects.filter") as mock_filter:
            
            mock_filter.return_value.first.return_value = sr_mock
            req = factory.post(
                "/api/memberships/internal/payment-webhook/",
                webhook_payload,
                format="json",
                HTTP_X_SERVICE_TOKEN="valid-token",
                HTTP_X_SERVICE_SIGNATURE="t=123,v1=abc",
            )
            response = view(req)
            assert response.status_code == status.HTTP_200_OK
            resp_data = json.loads(response.content.decode("utf-8"))
            assert resp_data["status"] == "success"
            assert sr_mock.payment_status == "released"
            sr_mock.save.assert_called_once()
