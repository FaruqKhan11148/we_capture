// ================= NAV TOGGLE =================
const navToggle = document.querySelector(".nav-toggle");
const navLinks = document.querySelector(".nav-links");

if (navToggle && navLinks) {
    navToggle.addEventListener("click", () => {
        const isOpen = navLinks.classList.toggle("is-open");
        navToggle.setAttribute("aria-expanded", String(isOpen));
    });
}


// ================= DOM READY =================
document.addEventListener("DOMContentLoaded", () => {

    // ================= OTP INPUT =================
    const inputs = document.querySelectorAll(".otp-container input");
    const hiddenInput = document.getElementById("otp");

    if (inputs.length && hiddenInput) {
        inputs.forEach((input, index) => {
            input.addEventListener("input", () => {
                if (input.value.length === 1 && index < inputs.length - 1) {
                    inputs[index + 1].focus();
                }

                let otp = "";
                inputs.forEach(i => otp += i.value);
                hiddenInput.value = otp;
            });
        });
    }
});

    // ================= STAR RATING =================
document.addEventListener("DOMContentLoaded", () => {
    const stars = document.querySelectorAll(".star-rating span");
    const input = document.getElementById("ratingInput");

    if (!stars.length || !input) return;

    let selectedRating = 0;

    stars.forEach((star, index) => {

        // CLICK
        star.addEventListener("click", () => {
            selectedRating = index + 1;

            stars.forEach((s, i) => {
                s.classList.toggle("active", i < selectedRating);
            });
        });

    });

    // 🔥 IMPORTANT: SET VALUE ON SUBMIT
    const form = document.querySelector(".review-form");

    if (form) {
        form.addEventListener("submit", () => {
            console.log("FINAL SUBMIT RATING:", selectedRating);
            input.value = selectedRating;
        });
    }
});


// ================= PASSWORD TOGGLE =================
function togglePassword(id) {
    const input = document.getElementById(id);
    if (!input) return;

    input.type = input.type === "password" ? "text" : "password";
}


// ================= QUERY MODAL =================
function openQuery() {
    document.getElementById("queryModal").style.display = "flex";
}

function closeQuery() {
    document.getElementById("queryModal").style.display = "none";
}


// ================= MEDIA MODAL =================
function openMedia(url, type) {
    let modal = document.getElementById("mediaModal");
    let container = document.getElementById("mediaContainer");

    if (!modal || !container) return;

    if (type === "image") {
        container.innerHTML = `<img src="${url}">`;
    } else {
        container.innerHTML = `
            <video controls autoplay>
                <source src="${url}" type="video/mp4">
            </video>
        `;
    }

    modal.style.display = "flex";
}

function closeMedia() {
    let modal = document.getElementById("mediaModal");
    let container = document.getElementById("mediaContainer");

    if (!modal || !container) return;

    modal.style.display = "none";
    container.innerHTML = "";
}


// ================= CLICK OUTSIDE =================
window.addEventListener("click", function(e) {
    let mediaModal = document.getElementById("mediaModal");
    let queryModal = document.getElementById("queryModal");

    if (mediaModal && e.target === mediaModal) closeMedia();
    if (queryModal && e.target === queryModal) closeQuery();
});


// ================= ESC CLOSE =================
document.addEventListener("keydown", function(e) {
    if (e.key === "Escape") {
        closeMedia();
        closeQuery();
    }
});


// ================= GALLERY TOGGLE =================
let expanded = false;

function toggleGallery() {
    let items = document.querySelectorAll(".hidden-media");
    let btn = document.getElementById("seeMoreBtn");

    if (!btn) return;

    if (!expanded) {
        items.forEach(item => item.style.display = "block");
        btn.innerText = "See Less";
        expanded = true;
    } else {
        items.forEach(item => item.style.display = "none");
        btn.innerText = "See More";
        expanded = false;
    }
}

// FORCE SET VALUE BEFORE SUBMIT
document.querySelector("form.review-form")?.addEventListener("submit", function() {
    const stars = document.querySelectorAll(".star-rating span.active");

    if (stars.length > 0) {
        document.getElementById("ratingInput").value = stars.length;
    }
});