Feature: Verify Basis Admin login to APX Dashboard

  Scenario: Basis Admin can log in and see dashboard
    I navigate to "http://apxtechnology.in:3000/"
    I enter "admin" into "User Id"
    I enter "password123" into "password"
    I click "Sign in to Dashboard"
    I should see text "ApxOps - SAP Monitoring Platform"
    I click on "sap Basis Admin"
    I should see button "Sign In to Dashboard"
