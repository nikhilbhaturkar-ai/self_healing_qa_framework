Feature: Verify admin can sign in to the APX OPS dashboard and see all Basis Monitoring tiles

  Scenario: Admin signs in and views Basis Monitoring tiles
    Given I navigate to "http://apxtechnology.in:3000/"
    And I enter "admin" into "User Id"
    And I enter "password123" into "password"
    And I click "Sign in to Dashboard"
    And I should see text "ApxOps - SAP Monitoring Platform"
    And I click on "SAP Basis Admin"
    And I should see all listed texts
      | text |
      | Basis Monitoring Tile 1 |
      | Basis Monitoring Tile 2 |
      | Basis Monitoring Tile 3 |
    And I click on "Sign out"
    And I should see button "Sign In to Dashboard"
