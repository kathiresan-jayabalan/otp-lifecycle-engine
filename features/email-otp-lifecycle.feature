@email-otp
Feature: Email OTP lifecycle
  Exercises email-delivered one-time passcodes against the control profile in
  control-profiles/otp-controls.yaml. Every scenario ends by evaluating the
  policy engine over the observed event stream for this scenario's subject
  and sealing an evidence bundle under evidence-runs/.

  Background:
    Given a fresh account with a matching email and phone

  @control:otp.replay-resistance
  Scenario: A consumed email code cannot be used a second time
    When I request an email verification code
    And I submit the received code
    Then the login should succeed
    And the submission should be rejected with reason "replay"
    And the control profile verdict for "otp.replay-resistance" should be "PASS"

  @control:otp.bounded-validity
  Scenario: An expired email code is rejected
    When I request an email verification code
    And the server clock advances past the code's expiry
    Then the submission should be rejected with reason "expired"
    And the control profile verdict for "otp.bounded-validity" should be "PASS"

  @control:otp.attempt-limit
  Scenario: Repeated invalid codes lock the account
    When I request an email verification code
    And I submit an incorrect code repeatedly until locked
    Then the account should be locked
    And the control profile verdict for "otp.attempt-limit" should be "PASS"

  @control:otp.session-binding
  Scenario: A code cannot be redeemed from a different session
    When I request an email verification code
    And a second browser session submits the same code
    Then the second session's submission should be rejected with reason "wrong_session"
    And the control profile verdict for "otp.session-binding" should be "PASS"

  @control:otp.supersession
  Scenario: Requesting a new code invalidates the previous one
    When I request an email verification code
    And I request a new email verification code before using the first
    Then the first code should be rejected as superseded
    And the control profile verdict for "otp.supersession" should be "PASS"
