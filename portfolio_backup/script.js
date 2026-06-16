document.addEventListener('DOMContentLoaded', function() {
    // Typing animation for terminal
    const typedText = document.querySelector('.typed-text');
    const cursor = document.querySelector('.cursor');
    
    const textArray = [
        "Welcome to my portfolio...",
        "I'm a Network Engineer...",
        "Cybersecurity Specialist...",
        "Web Developer...",
        "Let's build something amazing!"
    ];
    
    let textArrayIndex = 0;
    let charIndex = 0;
    let isDeleting = false;
    let isEnd = false;
    
    function type() {
        isEnd = false;
        const currentText = textArray[textArrayIndex];
        
        if (isDeleting) {
            typedText.textContent = currentText.substring(0, charIndex - 1);
            charIndex--;
        } else {
            typedText.textContent = currentText.substring(0, charIndex + 1);
            charIndex++;
        }
        
        if (!isDeleting && charIndex === currentText.length) {
            isEnd = true;
            isDeleting = true;
            setTimeout(type, 1500);
        } else if (isDeleting && charIndex === 0) {
            isDeleting = false;
            textArrayIndex++;
            if (textArrayIndex >= textArray.length) {
                textArrayIndex = 0;
            }
            setTimeout(type, 500);
        } else {
            const typingSpeed = isDeleting ? 50 : 100;
            const randomSpeed = Math.random() * 100;
            setTimeout(type, isEnd ? typingSpeed : typingSpeed + randomSpeed);
        }
    }
    
    setTimeout(type, 1500);
    
    // Animate skill bars
    const skills = document.querySelectorAll('.skill');
    
    function animateSkills() {
        skills.forEach(skill => {
            const level = skill.getAttribute('data-level');
            const skillBar = skill.querySelector('.skill-bar');
            skillBar.style.setProperty('--width', level + '%');
        });
    }
    
    // Intersection Observer for skills animation
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                animateSkills();
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.5 });
    
    const skillsSection = document.querySelector('.skills');
    if (skillsSection) {
        observer.observe(skillsSection);
    }
    
    // Mobile menu toggle
    const hamburger = document.querySelector('.hamburger');
    const navLinks = document.querySelector('.nav-links');
    
    hamburger.addEventListener('click', () => {
        navLinks.classList.toggle('active');
        hamburger.classList.toggle('active');
    });
    
    // Close mobile menu when clicking a link
    document.querySelectorAll('.nav-links a').forEach(link => {
        link.addEventListener('click', () => {
            navLinks.classList.remove('active');
            hamburger.classList.remove('active');
        });
    });
    
    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            
            const targetId = this.getAttribute('href');
            const targetElement = document.querySelector(targetId);
            
            if (targetElement) {
                window.scrollTo({
                    top: targetElement.offsetTop - 80,
                    behavior: 'smooth'
                });
            }
        });
    });
    
    // Form submission
    const contactForm = document.getElementById('contactForm');
    
    if (contactForm) {
        contactForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const name = formData.get('name');
            const email = formData.get('email');
            const subject = formData.get('subject');
            const message = formData.get('message');
            
            // Here you would typically send the form data to a server
            // For demonstration, we'll just show an alert
            alert(`Thank you, ${name}! Your message has been sent. I'll get back to you soon.`);
            
            // Reset form
            this.reset();
        });
    }
    
    // Matrix animation for hero background
    const matrixAnimation = document.querySelector('.matrix-animation');
    
    if (matrixAnimation) {
        // Create canvas for matrix animation
        const canvas = document.createElement('canvas');
        canvas.width = matrixAnimation.offsetWidth;
        canvas.height = matrixAnimation.offsetHeight;
        matrixAnimation.appendChild(canvas);
        
        const ctx = canvas.getContext('2d');
        
        // Set canvas to full width/height
        function resizeCanvas() {
            canvas.width = matrixAnimation.offsetWidth;
            canvas.height = matrixAnimation.offsetHeight;
        }
        
        window.addEventListener('resize', resizeCanvas);
        resizeCanvas();
        
        // Matrix characters - now using only alphanumeric and basic symbols
        const matrixChars = "01ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!@#$%^&*()_+-=[]{}|;:,.<>?";
        
        // Set font size and calculate columns
        const fontSize = 16;
        const columns = canvas.width / fontSize;
        
        // Create drops array
        const drops = [];
        for (let i = 0; i < columns; i++) {
            drops[i] = Math.random() * -100;
        }
        
        // Draw function
        function draw() {
            // Black background with opacity
            ctx.fillStyle = 'rgba(10, 10, 10, 0.05)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            
            // Set font and color
            ctx.fillStyle = '#00ff9d';
            ctx.font = fontSize + 'px monospace';
            
            // Loop over drops
            for (let i = 0; i < drops.length; i++) {
                // Get random character
                const text = matrixChars.charAt(Math.floor(Math.random() * matrixChars.length));
                
                // Draw character
                ctx.fillText(text, i * fontSize, drops[i] * fontSize);
                
                // Reset drop if it reaches bottom or randomly
                if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
                    drops[i] = 0;
                }
                
                // Move drop down
                drops[i]++;
            }
        }
        
        // Animation loop
        setInterval(draw, 33);
    }
});