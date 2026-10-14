Feature: APX OPS dashboard administration
  Verify administrator access, dashboard sections, monitoring tiles, and sign out.

  Background:
    Given I navigate to "http://apxtechnology.in:3000/"
    When I enter "admin" into "User Id"
    And I enter "password123" into "password"
    And I click "Sign in to Dashboard"
    Then I should see text "ApxOps - SAP Monitoring Platform"

  Scenario: Administrator can sign in to admin setting and sign out
    And I click on "sap Basis Admin"
    And I click on "Admin settings"
    Then I should see all listed texts
      | text                      |
      | Plan & Tile Configuration |
      | Users                     |
      | Email Notification        |
      | Company Settings          |
