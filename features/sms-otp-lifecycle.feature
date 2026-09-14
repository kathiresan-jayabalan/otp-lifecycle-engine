@sms-otp
Feature: SMS OTP lifecycle
  Same predicates as the email lifecycle, exercised over the SMS channel.
  Delivery goes through the local simulator by default (see
  demo-app/lib/channels/channelRouter.js); set MAILOSAUR_SMS_SERVER_ID and
  MAILOSAUR_API_KEY to route through a real Mailosaur SMS server instead.

  Background:
    Given a fresh account with a matching email and phone

  @control:otp.replay-resistance
  Scenario: A consumed SMS code cannot be used a second time
    When I request an sms verification code
    And I submit the received code
    Then the login should succeed
    And the submission should be rejected with reason "replay"
    And the control profile verdict for "otp.replay-resistance" should be "PASS"

  @control:otp.bounded-validity
  Scenario: An expired SMS code is rejected
    When I request an sms verification code
    And the server clock advances past the code's expiry
    Then the submission should be rejected with reason "expired"
    And the control profile verdict for "otp.bounded-validity" should be "PASS"

  @control:otp.attempt-limit
  Scenario: Repeated invalid SMS codes lock the account
    When I request an sms verification code
    And I submit an incorrect code repeatedly until locked
    Then the account should be locked
    And the control profile verdict for "otp.attempt-limit" should be "PASS"

  @control:otp.session-binding
  Scenario: An SMS code cannot be redeemed from a different session
    When I request an sms verification code
    And a second browser session submits the same code
    Then the second session's submission should be rejected with reason "wrong_session"
    And the control profile verdict for "otp.session-binding" should be "PASS"
