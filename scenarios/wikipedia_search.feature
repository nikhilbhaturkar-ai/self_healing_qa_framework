Feature: Wikipedia search
  Search Wikipedia and verify that the expected articles are present.

  Scenario Outline: Search Wikipedia for <search_term>
    Given I navigate to "https://en.wikipedia.org"
    When I enter "<search_term>" into "search"
    And I click "Search"
    Then I should see text "<expected_text>"

    Examples:
      | search_term | expected_text |
      | Google Pixel | Google Pixel |
      | Motorola | Motorola |