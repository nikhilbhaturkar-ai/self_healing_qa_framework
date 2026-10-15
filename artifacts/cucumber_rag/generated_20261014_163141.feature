Feature: Verify APX OPS dashboard access and Basis Monitoring tiles
  As an administrator
  I want to navigate to the APX OPS dashboard, sign in with admin credentials, and see the Basis Monitoring tiles

  Scenario: Administrator can view Basis Monitoring tiles
    Given I navigate to "http://apxtechnology.in:3000/"
    And I enter "admin" into "User Id"
    And I enter "password123" into "password"
    And I click "Sign in to Dashboard"
    Then I should see text "ApxOps - SAP Monitoring Platform"
    And I should see all listed texts
