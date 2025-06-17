function initAutocomplete() {
  const input = document.getElementById("id_full_address");
  if (!input || !window.google || !google.maps) return;

  const autocomplete = new google.maps.places.Autocomplete(input);

  autocomplete.addListener("place_changed", function () {
    const place = autocomplete.getPlace();
    if (!place || !place.address_components) {
      console.warn("❌ Немає даних про місце");
      return;
    }

    let country = "", city = "", street = "", postal_code = "";

    place.address_components.forEach(component => {
      const types = component.types;
      if (types.includes("country")) country = component.long_name;
      if (types.includes("locality")) city = component.long_name;
      if (types.includes("route")) street = component.long_name;
      if (types.includes("postal_code")) postal_code = component.long_name;
    });

    console.log("✅ Адреса:", { country, city, street, postal_code });

    // якщо хочеш заповнювати поля:
    if (document.getElementById("id_country")) document.getElementById("id_country").value = country;
    if (document.getElementById("id_city")) document.getElementById("id_city").value = city;
    if (document.getElementById("id_postal_code")) document.getElementById("id_postal_code").value = postal_code;
    if (document.getElementById("id_street")) document.getElementById("id_street").value = street;
  });
}

document.addEventListener("DOMContentLoaded", initAutocomplete);
