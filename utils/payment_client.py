import logging
from decimal import Decimal
from typing import Any, Dict, Optional
import requests
from django.conf import settings

logger = logging.getLogger("backend.payment_client")


class PaymentClientError(Exception):
    """Exception raised when an interaction with the Payment Microservice fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class PaymentServiceClient:
    """
    HTTP Client for synchronous service-to-service communication between
    the Jehostarter Monolith and the Payment Microservice.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.base_url = (
            base_url
            or getattr(settings, "PAYMENT_SERVICE_URL", "http://localhost:8001")
        ).rstrip("/")
        self.token = (
            token
            or getattr(settings, "PAYMENT_SERVICE_TOKEN", None)
            or getattr(settings, "INTERNAL_SERVICE_SECRET", "")
        )
        self.timeout = timeout

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Service-Token": self.token,
        }

    def create_payment(
        self,
        user_id: str,
        amount: Decimal,
        currency: str,
        purpose: str,
        resource_type: str,
        resource_id: str,
        idempotency_key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a Payment record in the Payment Microservice ledger.
        """
        url = f"{self.base_url}/payments/"
        payload = {
            "user_id": str(user_id),
            "amount": float(amount) if isinstance(amount, (Decimal, int, float)) else amount,
            "currency": str(currency).upper(),
            "purpose": str(purpose),
            "resource_type": str(resource_type),
            "resource_id": str(resource_id),
            "idempotency_key": str(idempotency_key),
            "metadata": metadata or {},
        }

        try:
            response = requests.post(
                url, json=payload, headers=self._headers, timeout=self.timeout
            )
        except requests.RequestException as e:
            logger.error(f"Failed to reach payment service at {url}: {e}")
            raise PaymentClientError(
                f"Payment service connection error: {str(e)}", status_code=503
            ) from e

        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            logger.warning(
                f"Payment service rejected create_payment (HTTP {response.status_code}): {detail}"
            )
            raise PaymentClientError(
                f"Payment service rejected create_payment (HTTP {response.status_code}): {detail}",
                status_code=response.status_code,
                response_data=detail,
            )

        return response.json()

    def initiate_payment(
        self,
        payment_id: str,
        provider: str = "stripe",
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
        customer_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Kick off provider-hosted checkout session (e.g. Stripe Checkout) for a Payment intent.
        Returns dictionary containing checkout_url, session_id, payment_id.
        """
        url = f"{self.base_url}/payments/{payment_id}/initiate/"
        payload = {
            "provider": provider,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "customer_email": customer_email,
        }

        try:
            response = requests.post(
                url, json=payload, headers=self._headers, timeout=self.timeout
            )
        except requests.RequestException as e:
            logger.error(f"Failed to reach payment service at {url}: {e}")
            raise PaymentClientError(
                f"Payment service connection error: {str(e)}", status_code=503
            ) from e

        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            logger.warning(
                f"Payment service rejected initiate_payment (HTTP {response.status_code}): {detail}"
            )
            raise PaymentClientError(
                f"Payment service rejected initiate_payment (HTTP {response.status_code}): {detail}",
                status_code=response.status_code,
                response_data=detail,
            )

        return response.json()

    def get_payment(self, payment_id: str) -> Dict[str, Any]:
        """
        Retrieve Payment details and status from the microservice.
        """
        url = f"{self.base_url}/payments/{payment_id}/"
        try:
            response = requests.get(
                url, headers=self._headers, timeout=self.timeout
            )
        except requests.RequestException as e:
            raise PaymentClientError(
                f"Payment service connection error: {str(e)}", status_code=503
            ) from e

        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise PaymentClientError(
                f"Payment service error (HTTP {response.status_code}): {detail}",
                status_code=response.status_code,
                response_data=detail,
            )

        return response.json()

    def sync_payment(self, payment_id: str) -> Dict[str, Any]:
        """
        Force active verification with the payment provider via the microservice.
        """
        url = f"{self.base_url}/payments/{payment_id}/sync/"
        try:
            response = requests.post(
                url, headers=self._headers, timeout=self.timeout
            )
        except requests.RequestException as e:
            raise PaymentClientError(
                f"Payment service connection error: {str(e)}", status_code=503
            ) from e

        if not response.ok:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise PaymentClientError(
                f"Payment service sync error (HTTP {response.status_code}): {detail}",
                status_code=response.status_code,
                response_data=detail,
            )

        return response.json()

    def create_hold(
        self,
        payment_id: str,
        provider: str = "stripe",
        payment_method_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        transfer_group: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Place a pre-authorization hold on a customer payment card (capture_method='manual')."""
        url = f"{self.base_url}/payments/{payment_id}/hold/"
        payload = {
            "provider": provider,
            "payment_method_id": payment_method_id,
            "customer_id": customer_id,
            "transfer_group": transfer_group,
        }
        try:
            res = requests.post(url, json=payload, headers=self._headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise PaymentClientError(f"Payment service connection error: {str(e)}", status_code=503) from e
        if not res.ok:
            detail = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
            raise PaymentClientError(f"Payment service hold error (HTTP {res.status_code}): {detail}", status_code=res.status_code, response_data=detail)
        return res.json()

    def capture_payment(
        self,
        payment_id: str,
        amount_to_capture: Optional[Decimal] = None,
        amount: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Capture actual funds from a previously authorized hold."""
        url = f"{self.base_url}/payments/{payment_id}/capture/"
        val = amount_to_capture if amount_to_capture is not None else amount
        payload = {}
        if val is not None:
            payload["amount_to_capture"] = float(val) if isinstance(val, (Decimal, int, float)) else val
        try:
            res = requests.post(url, json=payload, headers=self._headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise PaymentClientError(f"Payment service connection error: {str(e)}", status_code=503) from e
        if not res.ok:
            detail = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
            raise PaymentClientError(f"Payment service capture error (HTTP {res.status_code}): {detail}", status_code=res.status_code, response_data=detail)
        return res.json()

    def release_hold(
        self,
        payment_id: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Void / cancel an uncaptured authorization hold."""
        url = f"{self.base_url}/payments/{payment_id}/release/"
        payload = {"reason": reason}
        try:
            res = requests.post(url, json=payload, headers=self._headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise PaymentClientError(f"Payment service connection error: {str(e)}", status_code=503) from e
        if not res.ok:
            detail = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
            raise PaymentClientError(f"Payment service release error (HTTP {res.status_code}): {detail}", status_code=res.status_code, response_data=detail)
        return res.json()

    def transfer_funds(
        self,
        destination_account_id: Optional[str] = None,
        amount: Decimal = Decimal("0.00"),
        currency: str = "USD",
        source_payment_id: Optional[str] = None,
        transfer_group: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        destination_account: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transfer net funds directly to a connected provider/seller account."""
        url = f"{self.base_url}/transfers/"
        dest = destination_account_id or destination_account
        if not dest:
            raise PaymentClientError("destination_account_id is required", status_code=400)
        payload = {
            "destination_account_id": dest,
            "amount": float(amount) if isinstance(amount, (Decimal, int, float)) else amount,
            "currency": str(currency).upper(),
            "source_payment_id": source_payment_id,
            "transfer_group": transfer_group,
            "metadata": metadata or {},
        }
        try:
            res = requests.post(url, json=payload, headers=self._headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise PaymentClientError(f"Payment service connection error: {str(e)}", status_code=503) from e
        if not res.ok:
            detail = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
            raise PaymentClientError(f"Payment service transfer error (HTTP {res.status_code}): {detail}", status_code=res.status_code, response_data=detail)
        return res.json()

    def create_setup_intent(
        self,
        customer_email: Optional[str] = None,
        customer_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a SetupIntent to vault a card for future recurring / off-session billing."""
        url = f"{self.base_url}/payments/setup-intents/"
        payload = {
            "customer_email": customer_email,
            "customer_id": customer_id,
            "metadata": metadata or {},
        }
        try:
            res = requests.post(url, json=payload, headers=self._headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise PaymentClientError(f"Payment service connection error: {str(e)}", status_code=503) from e
        if not res.ok:
            detail = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
            raise PaymentClientError(f"Payment service SetupIntent error (HTTP {res.status_code}): {detail}", status_code=res.status_code, response_data=detail)
        return res.json()

    def create_connected_account(
        self,
        email: str,
        country: str = "US",
        account_type: str = "express",
        business_type: Optional[str] = "individual",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a Stripe Connect account for a driver, chaperone, or seller."""
        url = f"{self.base_url}/connect/accounts/"
        payload = {
            "email": email,
            "country": country,
            "account_type": account_type,
            "business_type": business_type,
            "metadata": metadata or {},
        }
        try:
            res = requests.post(url, json=payload, headers=self._headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise PaymentClientError(f"Payment service connection error: {str(e)}", status_code=503) from e
        if not res.ok:
            detail = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
            raise PaymentClientError(f"Payment service connect account error (HTTP {res.status_code}): {detail}", status_code=res.status_code, response_data=detail)
        return res.json()

    def create_account_link(
        self,
        account_id: str,
        refresh_url: str,
        return_url: str,
    ) -> Dict[str, Any]:
        """Create an onboarding link for a Stripe Connect account."""
        url = f"{self.base_url}/connect/accounts/link/"
        payload = {
            "account_id": account_id,
            "refresh_url": refresh_url,
            "return_url": return_url,
        }
        try:
            res = requests.post(url, json=payload, headers=self._headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise PaymentClientError(f"Payment service connection error: {str(e)}", status_code=503) from e
        if not res.ok:
            detail = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
            raise PaymentClientError(f"Payment service account link error (HTTP {res.status_code}): {detail}", status_code=res.status_code, response_data=detail)
        return res.json()

    def get_connected_account(
        self,
        account_id: str,
    ) -> Dict[str, Any]:
        """Fetch capabilities and status of a connected account."""
        url = f"{self.base_url}/connect/accounts/{account_id}/"
        try:
            res = requests.get(url, headers=self._headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise PaymentClientError(f"Payment service connection error: {str(e)}", status_code=503) from e
        if not res.ok:
            detail = res.json().get("detail", res.text) if res.headers.get("content-type") == "application/json" else res.text
            raise PaymentClientError(f"Payment service get connect account error (HTTP {res.status_code}): {detail}", status_code=res.status_code, response_data=detail)
        return res.json()


# Default singleton instance for usage across monolith applications
payment_client = PaymentServiceClient()

