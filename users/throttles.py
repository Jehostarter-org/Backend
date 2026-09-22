"""
Custom DRF throttle classes for auth endpoints.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class SignUpRateThrottle(AnonRateThrottle):
    scope = 'signup'
    rate = '3/hour'


class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'
    rate = '10/min'


class ForgotPasswordRateThrottle(AnonRateThrottle):
    scope = 'forgot_password'
    rate = '3/hour'


class ResendVerificationRateThrottle(UserRateThrottle):
    scope = 'resend_verification'
    rate = '3/hour'
