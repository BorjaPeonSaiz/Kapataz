"""Casos de uso ya compuestos que la API recibe de bootstrap.py."""

from dataclasses import dataclass

from kapataz.application.use_cases.authenticate_session import AuthenticateSession
from kapataz.application.use_cases.check_health import CheckHealth
from kapataz.application.use_cases.create_courtesy_account import CreateCourtesyAccount
from kapataz.application.use_cases.log_in import LogIn
from kapataz.application.use_cases.log_out import LogOut
from kapataz.application.use_cases.register_account import RegisterAccount
from kapataz.application.use_cases.stream_chat_reply import StreamChatReply
from kapataz.application.use_cases.verify_email import VerifyEmail
from kapataz.domain.clock import Clock


@dataclass(frozen=True, slots=True)
class AppServices:
    clock: Clock
    register_account: RegisterAccount
    verify_email: VerifyEmail
    log_in: LogIn
    log_out: LogOut
    authenticate_session: AuthenticateSession
    stream_chat_reply: StreamChatReply
    check_health: CheckHealth
    create_courtesy_account: CreateCourtesyAccount
