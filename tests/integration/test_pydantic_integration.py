"""Integration tests for Pydantic PII protection."""

import asyncio
import random
import string
from datetime import datetime
from typing import Annotated

import pytest
from pydantic import BaseModel, Field

from redactyl.detectors.mock import MockDetector
from redactyl.detectors.smart_mock import SmartMockDetector
from redactyl.pydantic_integration import (
    HallucinationError,
    HallucinationResponse,
    PIIConfig,
    PydanticPIIProtector,
    pii_field,
)
from redactyl.types import PIIEntity, PIIType

# ============= Input Models =============


class SimpleUser(BaseModel):
    """Simple user model for testing - kept for one same input/output test."""

    name: str
    email: str
    phone: str | None = None
    notes: str = ""


class ContactForm(BaseModel):
    """Input model for support ticket creation."""

    name: str
    email: str
    message: str
    urgent: bool = False


class UserProfile(BaseModel):
    """Input model for user profile processing."""

    full_name: str
    email: str
    phone: str
    bio: str
    preferences: dict[str, str] = Field(default_factory=dict)


class EmailMessage(BaseModel):
    """Input model for email processing."""

    sender_name: str
    sender_email: str
    recipient_email: str
    subject: str
    body: str
    attachments: list[str] = Field(default_factory=list)


class CustomerData(BaseModel):
    """Input model for order processing."""

    customer_name: str
    customer_email: str
    shipping_address: str
    billing_address: str
    items: list[dict[str, str]]
    notes: str = ""


class AnnotatedUser(BaseModel):
    """User model with PII field annotations - input."""

    name: Annotated[str, pii_field(PIIType.PERSON, parse_components=True)]
    email: Annotated[str, pii_field(PIIType.EMAIL)]
    phone: Annotated[str | None, pii_field(PIIType.PHONE)] = None
    bio: Annotated[str, pii_field(detect=False)] = ""  # Skip detection
    notes: str = ""  # Auto-detect


class NestedAddress(BaseModel):
    """Address model for nested testing."""

    street: str
    city: str
    country: str


class ComplexUser(BaseModel):
    """Complex user with nested models - input."""

    name: str
    email: str
    address: NestedAddress
    tags: list[str]
    metadata: dict[str, str]


# ============= Output Models =============


class SupportTicket(BaseModel):
    """Output model for support ticket creation."""

    ticket_id: str
    customer_name: str
    contact_email: str
    summary: str
    priority: str
    created_at: str
    status: str = "open"


class UserSummary(BaseModel):
    """Output model for user profile summary."""

    display_name: str
    contact_info: str
    profile_summary: str
    account_type: str
    tags: list[str] = Field(default_factory=list)


class EmailReply(BaseModel):
    """Output model for email reply generation."""

    to_name: str
    to_email: str
    from_email: str
    subject: str
    reply_body: str
    suggested_followup: str = ""


class ProcessedOrder(BaseModel):
    """Output model for order processing."""

    order_id: str
    customer_ref: str
    email_confirmation: str
    shipping_label: str
    total_items: int
    order_summary: str
    estimated_delivery: str


class ProfileAnalysis(BaseModel):
    """Output model for annotated user analysis."""

    user_id: str
    full_name: str
    communication_channel: str
    risk_score: float
    recommendations: list[str]


class LocationInfo(BaseModel):
    """Simplified location output."""

    display_address: str
    region: str
    postal_code: str = ""


class ComplexSummary(BaseModel):
    """Output model for complex user summary."""

    user_reference: str
    primary_contact: str
    location: LocationInfo
    categories: list[str]
    metadata_summary: str


class TestPydanticPIIProtector:
    """Test PydanticPIIProtector functionality."""

    def test_same_model_input_output(self):
        """Test protecting a model with same input/output type (for completeness)."""
        # Setup with smart detector that finds actual positions
        detector = SmartMockDetector(
            [
                ("John Doe", PIIType.PERSON),
                ("john@example.com", PIIType.EMAIL),
                ("John", PIIType.NAME_FIRST),  # For "Contact John soon"
            ]
        )
        protector = PydanticPIIProtector(detector, batch_detection=False)

        # Create model
        user = SimpleUser(
            name="John Doe",
            email="john@example.com",
            phone="555-1234",
            notes="Contact John soon",
        )

        # Protect
        protected, state = protector.protect_model(user)

        # Verify protection
        assert protected.name == "[NAME_FIRST_1] [NAME_LAST_1]"
        assert protected.email == "[EMAIL_1]"
        assert protected.phone == "555-1234"  # No entity detected
        assert "John" not in protected.notes  # Contains name

        # Verify state
        assert "[NAME_FIRST_1]" in state.tokens
        assert "[NAME_LAST_1]" in state.tokens
        assert "[EMAIL_1]" in state.tokens
        assert state.tokens["[NAME_FIRST_1]"].original == "John"
        assert state.tokens["[NAME_LAST_1]"].original == "Doe"
        assert state.tokens["[EMAIL_1]"].original == "john@example.com"

    def test_contact_form_to_ticket(self):
        """Test transforming ContactForm to SupportTicket with PII transfer."""
        # Setup detector
        detector = SmartMockDetector(
            [
                ("Jane Smith", PIIType.PERSON),
                ("jane@support.com", PIIType.EMAIL),
                ("Jane", PIIType.NAME_FIRST),
                ("Smith", PIIType.NAME_LAST),
            ]
        )
        protector = PydanticPIIProtector(detector, batch_detection=True)

        # Create input model
        form = ContactForm(
            name="Jane Smith",
            email="jane@support.com",
            message="I need help with my account. Please contact me ASAP.",
            urgent=True,
        )

        # Protect input
        protected_form, state = protector.protect_model(form)

        # Simulate transformation function (would be decorated in real use)
        ticket_id = f"TICKET-{random.randint(1000, 9999)}"
        protected_ticket = SupportTicket(
            ticket_id=ticket_id,
            customer_name=protected_form.name,  # PII transferred
            contact_email=protected_form.email,  # PII transferred
            summary=f"Urgent request from {protected_form.name}: {protected_form.message[:30]}...",
            priority="high" if protected_form.urgent else "normal",
            created_at=datetime.now().isoformat(),
            status="open",
        )

        # Unprotect output
        unprotected_ticket, issues = protector.unprotect_model(protected_ticket, state)

        # Verify PII was correctly transferred and restored
        assert unprotected_ticket.customer_name == "Jane Smith"
        assert unprotected_ticket.contact_email == "jane@support.com"
        assert "Jane Smith" in unprotected_ticket.summary
        assert unprotected_ticket.priority == "high"
        assert len(issues) == 0

    def test_user_profile_to_summary(self):
        """Test transforming UserProfile to UserSummary with field mapping."""
        # Setup detector
        detector = SmartMockDetector(
            [
                ("Robert Johnson", PIIType.PERSON),
                ("bob@example.com", PIIType.EMAIL),
                ("555-0123", PIIType.PHONE),
                ("Robert", PIIType.NAME_FIRST),
            ]
        )
        protector = PydanticPIIProtector(detector, batch_detection=True)

        # Create input model
        profile = UserProfile(
            full_name="Robert Johnson",
            email="bob@example.com",
            phone="555-0123",
            bio="Software engineer with 10 years experience. Contact Robert for consultations.",
            preferences={"notifications": "email", "language": "en"},
        )

        # Protect input
        protected_profile, state = protector.protect_model(profile)

        # Transform to summary (simulating LLM processing)
        # Note: protected_profile.bio will have "Robert" replaced with token
        protected_summary = UserSummary(
            display_name=f"User {protected_profile.full_name}",
            contact_info=f"Email: {protected_profile.email}, Phone: {protected_profile.phone}",
            profile_summary=f"Experienced professional: {protected_profile.bio[:60]}...",
            account_type="premium",
            tags=[
                "engineer",
                "consultant",
                protected_profile.full_name.split()[0],
            ],  # Using first name as tag
        )

        # Unprotect output
        unprotected_summary, issues = protector.unprotect_model(
            protected_summary, state
        )

        # Verify transformation
        assert "Robert Johnson" in unprotected_summary.display_name
        assert "bob@example.com" in unprotected_summary.contact_info
        assert "555-0123" in unprotected_summary.contact_info
        # The bio had "Robert" so after unprotection it should be restored
        assert (
            "Robert" in unprotected_summary.profile_summary
            or "[NAME_FIRST_" in protected_profile.bio
        )
        assert any(
            "Robert" in tag or "[NAME_FIRST_" in tag for tag in unprotected_summary.tags
        )
        assert len(issues) == 0

    def test_email_to_reply_generation(self):
        """Test transforming EmailMessage to EmailReply with new PII fields."""
        # Setup detector
        detector = SmartMockDetector(
            [
                ("Alice Cooper", PIIType.PERSON),
                ("alice@company.com", PIIType.EMAIL),
                ("support@company.com", PIIType.EMAIL),
                ("Alice", PIIType.NAME_FIRST),
            ]
        )
        protector = PydanticPIIProtector(detector, batch_detection=True)

        # Create input email
        email = EmailMessage(
            sender_name="Alice Cooper",
            sender_email="alice@company.com",
            recipient_email="support@company.com",
            subject="Account Issue",
            body="Hi, I'm Alice Cooper and I'm having trouble accessing my account.",
            attachments=["screenshot.png"],
        )

        # Protect input
        protected_email, state = protector.protect_model(email)

        # Generate reply (simulating LLM generating response)
        protected_reply = EmailReply(
            to_name=protected_email.sender_name,
            to_email=protected_email.sender_email,
            from_email=protected_email.recipient_email,
            subject=f"Re: {protected_email.subject}",
            reply_body=f"Dear {protected_email.sender_name},\n\nThank you for contacting us about your account issue. We'll help you resolve this promptly.\n\nBest regards,\nSupport Team",
            suggested_followup=f"Check if {protected_email.sender_name} needs password reset",
        )

        # Unprotect output
        unprotected_reply, issues = protector.unprotect_model(protected_reply, state)

        # Verify PII handling
        assert unprotected_reply.to_name == "Alice Cooper"
        assert unprotected_reply.to_email == "alice@company.com"
        assert unprotected_reply.from_email == "support@company.com"
        assert "Alice Cooper" in unprotected_reply.reply_body
        assert "Alice Cooper" in unprotected_reply.suggested_followup
        assert len(issues) == 0

    def test_customer_data_to_order(self):
        """Test transforming CustomerData to ProcessedOrder with field reduction."""
        # Setup detector
        detector = SmartMockDetector(
            [
                ("Michael Brown", PIIType.PERSON),
                ("michael@customer.com", PIIType.EMAIL),
                ("123 Main St, City", PIIType.ADDRESS),
                ("456 Oak Ave, Town", PIIType.ADDRESS),
            ]
        )
        protector = PydanticPIIProtector(detector, batch_detection=True)

        # Create customer data
        customer = CustomerData(
            customer_name="Michael Brown",
            customer_email="michael@customer.com",
            shipping_address="123 Main St, City",
            billing_address="456 Oak Ave, Town",
            items=[{"name": "Widget", "qty": "2"}, {"name": "Gadget", "qty": "1"}],
            notes="Please deliver to Michael Brown personally",
        )

        # Protect input
        protected_customer, state = protector.protect_model(customer)

        # Process order (simulating business logic)
        order_id = f"ORD-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
        protected_order = ProcessedOrder(
            order_id=order_id,
            customer_ref=protected_customer.customer_name,  # PII preserved
            email_confirmation=f"Confirmation sent to {protected_customer.customer_email}",
            shipping_label=f"Ship to: {protected_customer.shipping_address}",
            total_items=len(protected_customer.items),
            order_summary=f"Order for {protected_customer.customer_name}: {len(protected_customer.items)} items",
            estimated_delivery="3-5 business days",
        )

        # Unprotect output
        unprotected_order, issues = protector.unprotect_model(protected_order, state)

        # Verify PII handling - note that billing address is not in output
        assert unprotected_order.customer_ref == "Michael Brown"
        assert "michael@customer.com" in unprotected_order.email_confirmation
        assert "123 Main St, City" in unprotected_order.shipping_label
        assert "Michael Brown" in unprotected_order.order_summary
        assert "456 Oak Ave" not in str(
            unprotected_order
        )  # Billing address not transferred
        assert len(issues) == 0

    def test_nested_model_transformation(self):
        """Test transforming ComplexUser to ComplexSummary with nested structure changes."""
        # Setup
        entities = [
            PIIEntity(
                type=PIIType.PERSON,
                value="Alice Johnson",
                start=0,
                end=13,
                confidence=0.95,
            ),
            PIIEntity(
                type=PIIType.EMAIL,
                value="alice@example.com",
                start=14,
                end=31,
                confidence=0.98,
            ),
            PIIEntity(
                type=PIIType.ADDRESS,
                value="123 Main St",
                start=32,
                end=43,
                confidence=0.90,
            ),
        ]
        detector = MockDetector(entities)
        protector = PydanticPIIProtector(detector, batch_detection=True)

        # Create nested input model
        user = ComplexUser(
            name="Alice Johnson",
            email="alice@example.com",
            address=NestedAddress(
                street="123 Main St", city="Springfield", country="USA"
            ),
            tags=["developer", "Alice's team"],
            metadata={"created_by": "Alice", "department": "Engineering"},
        )

        # Protect input
        protected_user, state = protector.protect_model(user)

        # Transform to summary with different structure
        protected_summary = ComplexSummary(
            user_reference=f"USR-{protected_user.name}",
            primary_contact=protected_user.email,
            location=LocationInfo(
                display_address=f"{protected_user.address.street}, {protected_user.address.city}",
                region=f"{protected_user.address.city}, {protected_user.address.country}",
                postal_code="",  # Not available in input
            ),
            categories=protected_user.tags,
            metadata_summary=f"Created by {protected_user.metadata.get('created_by', 'unknown')} in {protected_user.metadata.get('department', 'unknown')}",
        )

        # Unprotect output
        unprotected_summary, issues = protector.unprotect_model(
            protected_summary, state
        )

        # Verify transformation
        assert "Alice Johnson" in unprotected_summary.user_reference
        assert unprotected_summary.primary_contact == "alice@example.com"
        assert "123 Main St" in unprotected_summary.location.display_address
        assert "Springfield" in unprotected_summary.location.region
        assert "Alice" in unprotected_summary.metadata_summary
        assert any("Alice" in cat for cat in unprotected_summary.categories)
        assert len(issues) == 0

    def test_unprotection_with_field_mapping(self):
        """Test unprotecting with different field names between input and output."""
        # Setup
        detector = SmartMockDetector(
            [
                ("Bob Williams", PIIType.PERSON),
                ("bob@example.com", PIIType.EMAIL),
            ]
        )
        protector = PydanticPIIProtector(detector, use_name_parsing=False)

        # Create and protect input model
        profile = UserProfile(
            full_name="Bob Williams",
            email="bob@example.com",
            phone="555-1234",
            bio="Senior developer",
        )
        protected_profile, state = protector.protect_model(profile)

        # Transform to different output model
        summary = UserSummary(
            display_name=protected_profile.full_name,  # Field name changed
            contact_info=f"{protected_profile.email}",  # Combined field
            profile_summary=f"Professional: {protected_profile.bio}",
            account_type="standard",
        )

        # Unprotect
        unprotected_summary, issues = protector.unprotect_model(summary, state)

        # Verify restoration with field mapping
        assert unprotected_summary.display_name == "Bob Williams"
        assert "bob@example.com" in unprotected_summary.contact_info
        assert len(issues) == 0

    def test_hallucination_handling(self):
        """Test handling of hallucinated tokens during unprotection."""
        # Setup
        detector = SmartMockDetector(
            [
                ("real@example.com", PIIType.EMAIL),
            ]
        )
        protector = PydanticPIIProtector(detector, fuzzy_unredaction=False)

        # Create and protect model
        original = SimpleUser(name="Test User", email="real@example.com")
        protected, state = protector.protect_model(original)

        # Simulate LLM hallucinating new tokens
        protected.notes = "Email [EMAIL_1] and CC [EMAIL_2] and [PHONE_1]"

        # Unprotect
        unprotected, issues = protector.unprotect_model(protected, state)

        # Verify hallucinations are detected
        assert len(issues) == 2  # EMAIL_2 and PHONE_1
        assert any(issue.token == "[EMAIL_2]" for issue in issues)
        assert any(issue.token == "[PHONE_1]" for issue in issues)

        # Verify known tokens are still replaced
        assert "real@example.com" in unprotected.notes
        assert "[EMAIL_2]" in unprotected.notes  # Hallucination preserved
        assert "[PHONE_1]" in unprotected.notes  # Hallucination preserved

    def test_field_annotations_with_transformation(self):
        """Test that field annotations are respected during model transformation."""
        # Setup
        entities = [
            PIIEntity(
                type=PIIType.PERSON,
                value="Carol Davis",
                start=0,
                end=11,
                confidence=0.95,
            ),
            PIIEntity(
                type=PIIType.EMAIL,
                value="carol@example.com",
                start=12,
                end=29,
                confidence=0.98,
            ),
        ]
        detector = MockDetector(entities)
        protector = PydanticPIIProtector(detector)

        # Create annotated input model
        user = AnnotatedUser(
            name="Carol Davis",
            email="carol@example.com",
            bio="Carol is a developer",  # Should be skipped due to detect=False
            notes="Contact Carol soon",
        )

        # Protect input
        protected_user, state = protector.protect_model(user)

        # Transform to analysis output
        analysis = ProfileAnalysis(
            user_id=f"ANALYST-{random.randint(1000, 9999)}",
            full_name=protected_user.name,
            communication_channel=f"Email: {protected_user.email}",
            risk_score=0.3,
            recommendations=[
                f"Monitor activity for {protected_user.name}",
                "Enable 2FA",
                protected_user.bio,  # This contains unredacted PII since detect=False
            ],
        )

        # Unprotect output
        unprotected_analysis, issues = protector.unprotect_model(analysis, state)

        # Verify transformation
        assert unprotected_analysis.full_name == "Carol Davis"
        assert "carol@example.com" in unprotected_analysis.communication_channel
        assert "Carol Davis" in unprotected_analysis.recommendations[0]
        assert (
            "Carol is a developer" in unprotected_analysis.recommendations[2]
        )  # Bio was not redacted
        assert len(issues) == 0

    def test_empty_model_handling(self):
        """Test handling of models with no string fields."""

        # Setup
        class NumericModel(BaseModel):
            age: int
            score: float
            active: bool

        detector = SmartMockDetector([])
        protector = PydanticPIIProtector(detector)

        # Create model with no strings
        model = NumericModel(age=30, score=95.5, active=True)

        # Protect
        protected, state = protector.protect_model(model)

        # Verify model unchanged
        assert protected.age == 30
        assert protected.score == 95.5
        assert protected.active is True
        assert len(state.tokens) == 0

    def test_consistent_tokens_across_fields(self):
        """Test that same entity gets same token across different fields."""
        # Setup with same email in multiple fields
        detector = SmartMockDetector(
            [
                ("shared@example.com", PIIType.EMAIL),
            ]
        )
        protector = PydanticPIIProtector(detector, batch_detection=True)

        # Create model with repeated PII
        user = SimpleUser(
            name="Test User",
            email="shared@example.com",
            notes="Reply to shared@example.com",
        )

        # Protect
        protected, state = protector.protect_model(user)

        # Verify same token used
        assert protected.email == "[EMAIL_1]"
        assert "[EMAIL_1]" in protected.notes
        assert protected.notes.count("[EMAIL_1]") == 1

        # Verify state has single mapping
        assert len([k for k in state.tokens if k.startswith("[EMAIL_")]) == 1


class TestPIIConfigDecorator:
    """Test the PIIConfig.protect decorator functionality."""

    def test_sync_function_with_different_models(self):
        """Test decorating a function that transforms between different models."""
        # Setup
        detector = SmartMockDetector(
            [
                ("David Brown", PIIType.PERSON),
                ("david@example.com", PIIType.EMAIL),
            ]
        )

        # Define decorated function using PIIConfig
        config = PIIConfig(detector=detector)

        @config.protect
        def create_support_ticket(form: ContactForm) -> SupportTicket:
            # Input should be protected
            assert "[NAME_" in form.name or "[PERSON_" in form.name
            assert form.email == "[EMAIL_1]"

            # Create ticket with transformed data
            ticket = SupportTicket(
                ticket_id=f"TICKET-{random.randint(1000, 9999)}",
                customer_name=form.name,
                contact_email=form.email,
                summary=f"Request from {form.name}: {form.message[:30]}...",
                priority="high" if form.urgent else "normal",
                created_at=datetime.now().isoformat(),
            )
            return ticket

        # Call with original model
        form_input = ContactForm(
            name="David Brown",
            email="david@example.com",
            message="Need help with account access",
            urgent=True,
        )

        result = create_support_ticket(form_input)

        # Verify result is unprotected
        assert result.customer_name == "David Brown"
        assert result.contact_email == "david@example.com"
        assert "David Brown" in result.summary
        assert result.priority == "high"

    @pytest.mark.asyncio
    async def test_async_function_with_email_transformation(self):
        """Test async function that transforms EmailMessage to EmailReply."""
        # Setup
        detector = SmartMockDetector(
            [
                ("Emma Wilson", PIIType.PERSON),
                ("emma@client.com", PIIType.EMAIL),
                ("support@service.com", PIIType.EMAIL),
            ]
        )

        # Define decorated async function using PIIConfig
        config = PIIConfig(detector=detector)

        @config.protect
        async def generate_email_reply(message: EmailMessage) -> EmailReply:
            # Simulate async operation (e.g., LLM call)
            await asyncio.sleep(0.01)

            # Input should be protected
            assert "[NAME_" in message.sender_name or "[PERSON_" in message.sender_name
            assert "[EMAIL_" in message.sender_email

            # Generate reply
            reply = EmailReply(
                to_name=message.sender_name,
                to_email=message.sender_email,
                from_email=message.recipient_email,
                subject=f"Re: {message.subject}",
                reply_body=f"Dear {message.sender_name},\n\nThank you for your message about '{message.subject}'.\n\nBest regards,\nSupport Team",
                suggested_followup=f"Schedule follow-up with {message.sender_name} if needed",
            )
            return reply

        # Call with original model
        original_message = EmailMessage(
            sender_name="Emma Wilson",
            sender_email="emma@client.com",
            recipient_email="support@service.com",
            subject="Product inquiry",
            body="I'm interested in your premium plan.",
        )

        result = await generate_email_reply(original_message)

        # Verify result is unprotected
        assert result.to_name == "Emma Wilson"
        assert result.to_email == "emma@client.com"
        assert "Emma Wilson" in result.reply_body
        assert "Emma Wilson" in result.suggested_followup

    def test_config_without_detector_uses_default(self):
        """Test that PIIConfig without detector uses default PresidioDetector."""
        # PIIConfig() now creates a default PresidioDetector with GLiNER
        config = PIIConfig()
        
        # Verify default detector was created
        from redactyl.detectors.presidio import PresidioDetector
        assert config.detector is not None
        assert isinstance(config.detector, PresidioDetector)
        assert config.detector.use_gliner_for_names is False  # Changed default from GLiNER to nameparser
        
        # Test that it works
        @config.protect
        def process_user(user: SimpleUser) -> SimpleUser:
            return user

        # Try to call it - should work with default detector
        result = process_user(SimpleUser(name="Test", email="test@example.com"))
        assert result  # Should work without error

    def test_mixed_model_transformation(self):
        """Test function with mixed BaseModel and non-BaseModel arguments."""
        # Setup
        detector = SmartMockDetector(
            [
                ("Test User", PIIType.PERSON),
                ("test@example.com", PIIType.EMAIL),
            ]
        )

        config = PIIConfig(detector=detector)

        @config.protect
        def process_order_with_metadata(
            customer: CustomerData, priority: int, tags: list[str], rush: bool
        ) -> ProcessedOrder:
            # Non-model args should be unchanged
            assert isinstance(priority, int)
            assert isinstance(tags, list)
            assert isinstance(rush, bool)

            # Customer should be protected
            assert (
                "[NAME_" in customer.customer_name
                or "[PERSON_" in customer.customer_name
            )

            # Create order with metadata in fields
            order = ProcessedOrder(
                order_id=f"RUSH-{priority}" if rush else f"STD-{priority}",
                customer_ref=customer.customer_name,
                email_confirmation=f"Sent to {customer.customer_email}",
                shipping_label=customer.shipping_address,
                total_items=len(customer.items),
                order_summary=f"Priority {priority} order for {customer.customer_name} - Tags: {','.join(tags)}",
                estimated_delivery="1-2 days" if rush else "3-5 days",
            )

            return order

        # Call with mixed arguments
        customer_input = CustomerData(
            customer_name="Test User",
            customer_email="test@example.com",
            shipping_address="123 Test St",
            billing_address="456 Bill Ave",
            items=[{"name": "Item1", "qty": "1"}],
        )

        result_order = process_order_with_metadata(
            customer_input, 1, ["urgent", "vip"], True
        )

        # Verify model is unprotected
        assert result_order.customer_ref == "Test User"
        assert "test@example.com" in result_order.email_confirmation
        assert result_order.order_id == "RUSH-1"
        assert "urgent,vip" in result_order.order_summary
        assert result_order.estimated_delivery == "1-2 days"

    def test_multiple_different_model_arguments(self):
        """Test function with multiple different BaseModel types."""
        # Setup
        detector = SmartMockDetector(
            [
                ("John Customer", PIIType.PERSON),
                ("john@customer.com", PIIType.EMAIL),
                ("Sarah Agent", PIIType.PERSON),
                ("agent@company.com", PIIType.EMAIL),
            ]
        )

        config = PIIConfig(
            detector=detector, batch_detection=True, use_name_parsing=False
        )

        @config.protect
        def merge_contact_and_email(
            contact: ContactForm, email: EmailMessage
        ) -> SupportTicket:
            # Both inputs should be protected
            assert contact.name == "[PERSON_1]"
            assert email.sender_name == "[PERSON_2]"

            # Create merged ticket
            ticket = SupportTicket(
                ticket_id=f"MERGED-{random.randint(1000, 9999)}",
                customer_name=contact.name,
                contact_email=contact.email,
                summary=f"Form from {contact.name}, Email from {email.sender_name}: {contact.message[:20]}...",
                priority="high",
                created_at=datetime.now().isoformat(),
            )
            return ticket

        # Create test inputs
        form = ContactForm(
            name="John Customer", email="john@customer.com", message="Need urgent help"
        )
        email_msg = EmailMessage(
            sender_name="Sarah Agent",
            sender_email="agent@company.com",
            recipient_email="support@company.com",
            subject="Escalation",
            body="Customer needs immediate assistance",
        )

        result = merge_contact_and_email(form, email_msg)

        # Verify unprotection handled both models
        assert result.customer_name == "John Customer"
        assert "John Customer" in result.summary
        assert "Sarah Agent" in result.summary


class TestNameComponentParsing:
    """Test name component parsing functionality."""

    def test_name_component_detection(self):
        """Test detection and tokenization of name components."""
        # Setup with a detector that parses names
        detector = SmartMockDetector(
            [
                ("Dr. Sarah Johnson", PIIType.PERSON),  # Will be parsed into components
                ("sarah@example.com", PIIType.EMAIL),
            ]
        )
        protector = PydanticPIIProtector(detector, use_name_parsing=True)

        # Create model with full name
        user = SimpleUser(
            name="Dr. Sarah Johnson",
            email="sarah@example.com",
            notes="Ask Dr. Johnson about the project",
        )

        # Protect
        protected, state = protector.protect_model(user)

        # Verify component tokenization
        # Entity tracker assigns indices by document order: "Dr." -> 1, "Sarah" -> 1, "Johnson" -> 1
        assert protected.name == "[NAME_TITLE_1] [NAME_FIRST_1] [NAME_LAST_1]"

        # Verify state has all component tokens
        assert "[NAME_TITLE_1]" in state.tokens
        assert "[NAME_FIRST_1]" in state.tokens
        assert "[NAME_LAST_1]" in state.tokens

        # Verify original values preserved
        assert state.tokens["[NAME_TITLE_1]"].original == "Dr."
        assert state.tokens["[NAME_FIRST_1]"].original == "Sarah"
        assert state.tokens["[NAME_LAST_1]"].original == "Johnson"

    def test_partial_name_usage(self):
        """Test handling of partial name usage (e.g., first name only)."""
        # Setup with smart detector
        detector = SmartMockDetector(
            [
                ("Jane Doe", PIIType.PERSON),  # Will be parsed if name parsing enabled
                ("Jane", PIIType.NAME_FIRST),
                ("Doe", PIIType.NAME_LAST),
            ]
        )
        protector = PydanticPIIProtector(detector, use_name_parsing=True)

        # Create model
        user = SimpleUser(
            name="Support Team",
            email="support@example.com",
            notes="Sincerely, Jane Doe",
        )

        # Protect
        protected, state = protector.protect_model(user)

        # Check what tokens were actually created
        # Entity tracker assigns indices by document order: "Jane" -> 1, "Doe" -> 1
        assert "[NAME_FIRST_1]" in state.tokens
        assert "[NAME_LAST_1]" in state.tokens

        # Simulate LLM using the actual tokens
        protected.notes = (
            "Dear [NAME_FIRST_1], thank you for your message. - [NAME_LAST_1]"
        )

        # Unprotect
        unprotected, issues = protector.unprotect_model(protected, state)

        # Verify correct restoration
        assert "Dear Jane" in unprotected.notes
        assert "- Doe" in unprotected.notes
        assert len(issues) == 0


class TestPIIConfig:
    """Test PIIConfig class functionality."""

    def test_config_with_complex_transformation(self):
        """Test PIIConfig with complex model transformation."""
        # Setup
        detector = SmartMockDetector(
            [
                ("Frank Miller", PIIType.PERSON),
                ("frank@example.com", PIIType.EMAIL),
                ("555-9876", PIIType.PHONE),
            ]
        )

        config = PIIConfig(detector=detector)

        # Use config.protect decorator for transformation
        @config.protect
        def transform_profile_to_summary(profile: UserProfile) -> UserSummary:
            # Should be protected inside
            assert "[NAME_" in profile.full_name or "[PERSON_" in profile.full_name
            assert "[EMAIL_" in profile.email
            assert "[PHONE_" in profile.phone

            # Transform to summary
            summary = UserSummary(
                display_name=f"User: {profile.full_name}",
                contact_info=f"Email: {profile.email}, Phone: {profile.phone}",
                profile_summary=f"Bio: {profile.bio[:50]}...",
                account_type="premium"
                if "premium" in profile.preferences.get("tier", "")
                else "standard",
                tags=[profile.full_name.split()[0], "active"],  # Use first name as tag
            )
            return summary

        # Test with original profile
        original = UserProfile(
            full_name="Frank Miller",
            email="frank@example.com",
            phone="555-9876",
            bio="Experienced software architect with focus on distributed systems",
            preferences={"tier": "premium", "notifications": "email"},
        )

        result = transform_profile_to_summary(original)

        # Should be unprotected in result
        assert "Frank Miller" in result.display_name
        assert "frank@example.com" in result.contact_info
        assert "555-9876" in result.contact_info
        assert any("Frank" in tag or "[NAME_FIRST_" in tag for tag in result.tags)

    def test_config_with_hallucination_in_transformation(self):
        """Test PIIConfig with hallucination callback during model transformation."""
        # Setup
        detector = SmartMockDetector(
            [
                ("Grace Lee", PIIType.PERSON),
                ("grace@example.com", PIIType.EMAIL),
            ]
        )

        hallucination_calls = []

        def handle_hallucinations(issues):
            """Track hallucinations and handle based on type."""
            hallucination_calls.append(issues)
            responses = []
            for issue in issues:
                if "EMAIL" in issue.token:
                    responses.append(HallucinationResponse.replace("[REDACTED_EMAIL]"))
                elif "PHONE" in issue.token:
                    responses.append(HallucinationResponse.replace("[REDACTED_PHONE]"))
                elif "SSN" in issue.token:
                    responses.append(HallucinationResponse.throw())
                else:
                    responses.append(HallucinationResponse.preserve())
            return responses

        config = PIIConfig(detector=detector, on_hallucination=handle_hallucinations)

        @config.protect
        def process_email_to_reply(email: EmailMessage) -> EmailReply:
            # Simulate LLM hallucinating additional PII tokens
            reply = EmailReply(
                to_name=email.sender_name,
                to_email=email.sender_email,
                from_email="noreply@company.com",
                subject=f"Re: {email.subject}",
                reply_body=f"""Dear {email.sender_name},
                
                Thank you for contacting us. We've received your message.
                
                For verification, we have your email as {email.sender_email}.
                Our callback number is [PHONE_1] (available 9-5 PST).
                Alternative email: [EMAIL_2]
                
                Best regards,
                Support Team""",
                suggested_followup=f"Call {email.sender_name} at [PHONE_2] if urgent",
            )
            return reply

        # Test
        original_email = EmailMessage(
            sender_name="Grace Lee",
            sender_email="grace@example.com",
            recipient_email="support@company.com",
            subject="Account question",
            body="Please help with my account settings.",
        )

        result = process_email_to_reply(original_email)

        # Verify callback was called
        assert len(hallucination_calls) == 1
        issues = hallucination_calls[0]
        assert len(issues) == 3  # PHONE_1, EMAIL_2, and PHONE_2 are hallucinations

        # Verify replacements applied
        assert "Grace Lee" in result.reply_body
        assert "grace@example.com" in result.reply_body
        assert "[REDACTED_PHONE]" in result.reply_body  # PHONE_1 replaced
        assert "[REDACTED_EMAIL]" in result.reply_body  # EMAIL_2 replaced
        assert "[REDACTED_PHONE]" in result.suggested_followup  # PHONE_2 replaced

    def test_config_hallucination_throw_action(self):
        """Test THROW action in hallucination handling."""
        # Setup
        detector = SmartMockDetector(
            [
                ("safe@example.com", PIIType.EMAIL),
            ]
        )

        config = PIIConfig(
            detector=detector,
            on_hallucination=lambda issues: [
                HallucinationResponse.throw() for _ in issues
            ],
        )

        @config.protect
        def process_with_strict_checking(user: SimpleUser) -> SimpleUser:
            result = user.model_copy()
            result.notes = "Email [EMAIL_1] and [EMAIL_2]"  # EMAIL_2 is hallucinated
            return result

        # Test - should raise exception
        original = SimpleUser(name="Test", email="safe@example.com")

        with pytest.raises(HallucinationError) as exc_info:
            process_with_strict_checking(original)

        # Verify exception details
        assert "[EMAIL_2]" in str(exc_info.value)
        assert len(exc_info.value.issues) == 1

    def test_config_with_all_options(self):
        """Test PIIConfig with all configuration options."""
        # Setup
        detector = SmartMockDetector(
            [
                ("Grace Chen", PIIType.PERSON),
            ]
        )

        handled_issues = []

        config = PIIConfig(
            detector=detector,
            batch_detection=False,  # Disable batch
            use_name_parsing=True,  # Keep name parsing enabled (it's still being used)
            fuzzy_unredaction=True,  # Enable fuzzy
            on_hallucination=lambda issues: (
                handled_issues.extend(issues),
                [HallucinationResponse.preserve() for _ in issues],
            )[1],
        )

        @config.protect
        def process_custom(user: SimpleUser) -> SimpleUser:
            # With name parsing, should get name component tokens
            assert "[NAME_FIRST_" in user.name or "[NAME_LAST_" in user.name
            return user

        # Test
        original = SimpleUser(name="Grace Chen", email="grace@example.com")

        result = process_custom(original)

        # Verify original restored
        assert result.name == "Grace Chen"

    @pytest.mark.asyncio
    async def test_async_order_processing(self):
        """Test async function transforming CustomerData to ProcessedOrder."""
        # Setup
        detector = SmartMockDetector(
            [
                ("Async Customer", PIIType.PERSON),
                ("async@customer.com", PIIType.EMAIL),
                ("789 Async St", PIIType.ADDRESS),
            ]
        )

        config = PIIConfig(detector=detector)

        @config.protect
        async def async_process_order(customer: CustomerData) -> ProcessedOrder:
            # Simulate async operations (DB lookup, external API, etc.)
            await asyncio.sleep(0.01)

            # Verify protection
            assert (
                "[NAME_" in customer.customer_name
                or "[PERSON_" in customer.customer_name
            )
            assert "[EMAIL_" in customer.customer_email
            assert "[ADDRESS_" in customer.shipping_address

            # Process order
            order = ProcessedOrder(
                order_id=f"ASYNC-{random.randint(10000, 99999)}",
                customer_ref=customer.customer_name,
                email_confirmation=f"Confirmation sent to {customer.customer_email}",
                shipping_label=f"Ship to: {customer.shipping_address}",
                total_items=len(customer.items),
                order_summary=f"Async order for {customer.customer_name}",
                estimated_delivery="2-3 business days",
            )
            return order

        # Test
        original_customer = CustomerData(
            customer_name="Async Customer",
            customer_email="async@customer.com",
            shipping_address="789 Async St",
            billing_address="Same as shipping",
            items=[{"name": "AsyncWidget", "qty": "3"}],
        )

        result = await async_process_order(original_customer)

        # Verify unprotection
        assert result.customer_ref == "Async Customer"
        assert "async@customer.com" in result.email_confirmation
        assert "789 Async St" in result.shipping_label
        assert "Async Customer" in result.order_summary

    def test_config_preserve_action(self):
        """Test PRESERVE action keeps hallucinated tokens."""
        # Setup
        detector = SmartMockDetector(
            [
                ("known@example.com", PIIType.EMAIL),
            ]
        )

        config = PIIConfig(
            detector=detector,
            on_hallucination=lambda issues: [
                HallucinationResponse.preserve() for _ in issues
            ],
        )

        @config.protect
        def process_preserve(user: SimpleUser) -> SimpleUser:
            result = user.model_copy()
            result.notes = "Email [EMAIL_1] and unknown [EMAIL_99]"
            return result

        # Test
        original = SimpleUser(name="User", email="known@example.com")

        result = process_preserve(original)

        # Verify known token replaced, unknown preserved
        assert "known@example.com" in result.notes
        assert "[EMAIL_99]" in result.notes  # Preserved as-is

    def test_config_mixed_hallucination_actions(self):
        """Test different actions for different hallucinated tokens."""
        # Setup
        detector = SmartMockDetector(
            [
                ("real@example.com", PIIType.EMAIL),
            ]
        )

        def mixed_handler(issues):
            """Handle different token types differently."""
            responses = []
            for issue in issues:
                if "[EMAIL_" in issue.token:
                    # Replace unknown emails with placeholder
                    responses.append(HallucinationResponse.replace("[REDACTED]"))
                elif "[PHONE_" in issue.token:
                    # Remove phone tokens entirely
                    responses.append(HallucinationResponse.ignore())
                elif "[SSN_" in issue.token:
                    # Throw on SSN tokens (strict security)
                    responses.append(HallucinationResponse.throw())
                else:
                    # Preserve everything else
                    responses.append(HallucinationResponse.preserve())
            return responses

        config = PIIConfig(detector=detector, on_hallucination=mixed_handler)

        @config.protect
        def process_mixed(user: SimpleUser) -> SimpleUser:
            result = user.model_copy()
            # Mix of real and hallucinated tokens
            result.notes = "Contact [EMAIL_1], [EMAIL_2], [PHONE_1], [NAME_1]"
            return result

        # Test normal case
        original = SimpleUser(name="Test", email="real@example.com")

        result = process_mixed(original)

        # Verify transformations
        assert "real@example.com" in result.notes  # Real email restored
        assert "[REDACTED]" in result.notes  # Hallucinated email replaced
        assert "[PHONE_1]" not in result.notes  # Phone removed
        assert "[NAME_1]" in result.notes  # Name preserved

        # Test SSN triggers exception
        @config.protect
        def process_with_ssn(user: SimpleUser) -> SimpleUser:
            result = user.model_copy()
            result.notes = "SSN: [SSN_1]"
            return result

        with pytest.raises(HallucinationError):
            process_with_ssn(original)

    def test_config_without_hallucination_callback(self):
        """Test PIIConfig without hallucination callback uses default behavior."""
        # Setup
        detector = SmartMockDetector(
            [
                ("test@example.com", PIIType.EMAIL),
            ]
        )

        config = PIIConfig(detector=detector)

        @config.protect
        def process_default(user: SimpleUser) -> SimpleUser:
            result = user.model_copy()
            # Hallucinated token
            result.notes = "Email [EMAIL_1] and [EMAIL_2]"
            return result

        # Capture warnings
        import warnings

        with warnings.catch_warnings(record=True) as w:
            # Ensure all warnings are captured
            warnings.simplefilter("always")

            # Test
            original = SimpleUser(name="Test", email="test@example.com")

            result = process_default(original)

            # Should still work but preserve hallucinated tokens
            assert "test@example.com" in result.notes
            assert "[EMAIL_2]" in result.notes  # Preserved by default

            # Check that warning was issued
            assert len(w) > 0, "Should have issued a warning"
            warning_message = str(w[0].message)
            assert "PII unredaction issue" in warning_message
            assert "[EMAIL_2]" in warning_message


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-xvs"])
