Feature: APX OPS dashboard administration
  Verify administrator access, dashboard sections, monitoring tiles, and sign out.

  Background:
    Given I navigate to "http://apxtechnology.in:3000/"
    When I enter "admin" into "User Id"
    And I enter "password123" into "password"
    And I click "Sign in to Dashboard"
    Then I should see text "ApxOps - SAP Monitoring Platform"

  Scenario: Administrator can sign in and sign out
    And I click on "sap Basis Admin"
    And I click on "sign out"
    And I should see button "Sign In to Dashboard"

  Scenario: Dashboard controls are available
    Then I should see all listed texts
      | text              |
      | SAP Basis Admin   |
      | PRIORITY FILTER   |
      | VIEW DATE         |
      | LATEST RUN        |
      | Basis Monitoring  |
      | System Monitoring |
      | IDoc Monitoring   |
      | History log       |
      | Reporting         |
    And I click on "SAP Basis Admin Lead Administrator"
    And I click on "Sign out"
    Then I should see button "Sign In to Dashboard"

  Scenario: Basis Monitoring tiles are displayed
    Then I should see all listed texts
      | text                                          |
      | DBA Cockpit - Data Volume                     |
      | DBA Cockpit - Log Volume                      |
      | Free Memory App Server                        |
      | Free Memory - Database                        |
      | STRUST - SSL Certificates Expired             |
      | STRUST - SSL Certificates Expired Today       |
      | STRUST - SSL Certificates Expiring in 15 Days |
      | Backup                                        |
      | SM13 - Update Requests                        |
      | SM12 - Lock Entries                           |
      | SM51 - Application Servers                    |
      | SM50 - Work Process List                      |
      | ST06 - OS Monitoring                          |
      | SM37 - Background Jobs                        |
      | SMQ1 - Outbound Queues                        |
      | SMQ2 - Inbound Queues                         |
      | SM20 - Security Audit Log                     |
      | SM21 - System Log                             |
      | SM58 - Transactional RFC                      |
      | Cancelled Jobs                                |
      | ST22 - ABAP Runtime Errors                    |
    And I click on "SAP Basis Admin"
    And I click on "Sign out"
    Then I should see button "Sign In to Dashboard"

  Scenario: System Monitoring tiles are displayed
    Then I click on "System Monitoring"
    Then I should see all listed texts
      | text                 |
      | Locked Users         |
      | Inactive Users       |
      | High Privilege Users |
      | Unassigned Roles     |
      | Unused Roles (Ghost) |
      | Unused Profiles      |
      | Unused T-Codes       |
      | Undeleted Users      |
      | Redundant Roles      |
      | Empty Shell Users    |
    And I click on "SAP Basis Admin"
    And I click on "Sign out"
    Then I should see button "Sign In to Dashboard"

  Scenario: Excel, Pdf and Emails buttons are displayed
    Then I click on "Excel"
    And I click on "Email"
    And I click on "Pdf"