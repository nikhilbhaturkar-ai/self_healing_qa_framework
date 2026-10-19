Feature: Verify login for user nikhil
  Scenario: User nikhil logs into APX dashboard
    Given I navigate to "http://apxtechnology.in:3000/"
    And I enter "nikhil" into "User Id"
    And I enter "password123" into "password"
    And I click "Sign in to Dashboard"
    Then I should see [text] "ApxOps - SAP Monitoring Platform"
    And I should see all listed texts
      | text |
      | Sample Text |
