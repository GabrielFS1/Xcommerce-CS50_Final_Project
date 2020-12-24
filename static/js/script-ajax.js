var stripe = Stripe("pk_test_51HwYy6G6XMWha81q2kZU5sEWdEvjfFBgj06py2OBLL3B8dT30nHT4NwDOu003VeOzxpkjQLvHUPRXCJNz0VSVj0t00EMmrvoiP");

var checkoutButton = document.getElementById("checkout-button");

checkoutButton.addEventListener("click", function () {
    fetch("/create-checkout-session", {
      method: "POST",
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (session) {
        return stripe.redirectToCheckout({ sessionId: session.id });
      })
      .then(function (result) {
        // If redirectToCheckout fails due to a browser or network
        // error, you should display the localized error message to your
        // customer using error.message.
        if (result.error) {
          alert(result.error.message);
        }
      })
      .catch(function (error) {
        console.error("Error:", error);
      });
  });