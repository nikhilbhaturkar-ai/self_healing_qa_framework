Feature: Verify admin can view company settings in admin settings
  As an admin user
  I want to see the company settings option in the admin settings page
  So that I can manage company configuration

  Scenario: Admin sees company settings button
    Given I navigate to "http://apxtechnology.in:3000/"
    And I enter "admin" into "User Id"
    And I enter "password123" into "password"
    And I click "Sign in to Dashboard"
    And I click "Admin Settings"
    Then I should see button "Company Settings"
