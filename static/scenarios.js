/* Scripted sessions for screenshots (open with ?scenario=<name>&figure=1). Steps act on the latest
   answer: ask (typed question, with the selected products), facet [attr, value] (filters in place),
   expand <brand> (view change), price <model name>, followup <index>, view cards|list|table, select <model name>
   (attaches it to the next question), open <model name> (product page), type <text> (into the composer,
   not sent), sort <attr:dir>, close (the product page), cart (adds the cheapest offer of an offers answer).
   A badge labels the step in the figure. */
window.SCENARIOS = {
  // Figure in the paper: aggregation that facets cannot express, drill-down within the table,
  // and a facet inside the answer whose click filters the answer in place.
  paper: [
    { ask: "Which brands offer the most battery life per euro among lightweight laptops?", badge: "1" },
    { expand: "Lumo", badge: "3" },
    { facet: ["ram_gb", 16], badge: "2" },
  ],
  // Product cards and a click on a price that becomes a turn.
  cards: [
    { ask: "Which lightweight laptops under €1,000 have the longest battery life?", badge: "1" },
    { price: "Vela Air 14", badge: "2" },
  ],
  // The shopping task of the paper and the storyboard (scripts/storyboards.py). Badges are the step numbers
  // of the paper: (1) is the opening answer; (2) to (10) follow.
  shopping: [
    { ask: "Which brands offer the most battery life per euro among lightweight laptops?", badge: "2" },
    { facet: ["ram_gb", 16], badge: "3" },
    { expand: "Lumo", badge: "4" },
    { ask: "Which lightweight laptops under €1,000 available for delivery tomorrow have the longest battery life?", badge: "5" },
    { open: "Aero 13" },
    { select: "Aero 13" },
    { close: true },
    { select: "Lumo Air 13" },
    { open: "Aero 14" },
    { type: "Which of them is the lightest?" },
    { ask: "Which of them is the lightest?", badge: "8" },
    { price: "Lumo Air 13", badge: "9" },
    { cart: true },
  ],
  // Typed refinement of the previous answer.
  refine: [
    { ask: "Which lightweight laptops under €1,000 have the longest battery life?" },
    { ask: "only with 16 GB RAM" },
    { view: "table" },
  ],
};
