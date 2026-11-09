from django.db import transaction
from rest_framework import serializers
from .sla import get_request_sla, start_request_sla
from .models import (
    Approval,
    Request,
    RequestActivity,
    RequestAttachment,
    RequestComment,
    RequestType,
)


class RequestTypeSerializer(serializers.ModelSerializer):

    class Meta:
        model = RequestType
        fields = ["id", "name", "code", "description"]


class RequestAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = RequestAttachment
        fields = [
            "id",
            "file",
            "file_url",
            "original_name",
            "content_type",
            "file_size",
            "uploaded_by",
            "uploaded_by_name",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "file_url",
            "original_name",
            "content_type",
            "file_size",
            "uploaded_by",
            "uploaded_by_name",
            "created_at",
        ]

    def get_uploaded_by_name(self, obj):
        if not obj.uploaded_by:
            return None
        full_name = f"{obj.uploaded_by.first_name} {obj.uploaded_by.last_name}".strip()
        return full_name or obj.uploaded_by.email or obj.uploaded_by.username

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url


class RequestCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = RequestComment
        fields = ["id", "author", "author_name", "message", "created_at", "updated_at"]
        read_only_fields = ["id", "author", "author_name", "created_at", "updated_at"]

    def get_author_name(self, obj):
        if not obj.author:
            return None
        full_name = f"{obj.author.first_name} {obj.author.last_name}".strip()
        return full_name or obj.author.email or obj.author.username

    def validate_message(self, value):
        message = value.strip()
        if not message:
            raise serializers.ValidationError("Le commentaire ne peut pas être vide.")
        return message


class RequestActivitySerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = RequestActivity
        fields = [
            "id",
            "type",
            "type_display",
            "title",
            "description",
            "metadata",
            "actor",
            "actor_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_name(self, obj):
        if not obj.actor:
            return "Système"
        full_name = f"{obj.actor.first_name} {obj.actor.last_name}".strip()
        return full_name or obj.actor.email or obj.actor.username


class ApprovalHistorySerializer(serializers.ModelSerializer):
    approver_name = serializers.SerializerMethodField()
    decision_display = serializers.CharField(source="get_decision_display", read_only=True)

    class Meta:
        model = Approval
        fields = [
            "id",
            "step",
            "required_role",
            "approver",
            "approver_name",
            "decision",
            "decision_display",
            "comment",
            "created_at",
            "decided_at",
        ]
        read_only_fields = fields

    def get_approver_name(self, obj):
        if not obj.approver:
            return None
        full_name = f"{obj.approver.first_name} {obj.approver.last_name}".strip()
        return full_name or obj.approver.email or obj.approver.username


class RequestSerializer(serializers.ModelSerializer):
    sla = serializers.SerializerMethodField()

    def get_sla(self, obj):
        return get_request_sla(obj)

    request_type_name = serializers.CharField(source="request_type.name", read_only=True)
    creator_name = serializers.SerializerMethodField()
    department_name = serializers.CharField(source="department.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    current_required_role = serializers.SerializerMethodField()
    approvals = ApprovalHistorySerializer(many=True, read_only=True)
    attachments = RequestAttachmentSerializer(many=True, read_only=True)
    comments = RequestCommentSerializer(many=True, read_only=True)
    activities = RequestActivitySerializer(many=True, read_only=True)

    class Meta:
        model = Request
        fields = [
            "id",
            "request_type",
            "request_type_name",
            "title",
            "description",
            "priority",
            "priority_display",
            "status",
            "status_display",
            "approval_step",
            "total_approval_steps",
            "current_required_role",
            "approvals",
            "attachments",
            "comments",
            "activities",
            "data",
            "creator",
            "creator_name",
            "department",
            "department_name",
            "created_at",
            "updated_at",
            "completed_at",
            "sla",
        ]
        read_only_fields = [
            "id",
            "creator",
            "status",
            "approval_step",
            "total_approval_steps",
            "current_required_role",
            "approvals",
            "attachments",
            "comments",
            "activities",
            "created_at",
            "updated_at",
            "completed_at",
            "sla",
        ]

    def get_creator_name(self, obj):
        if not obj.creator:
            return None
        full_name = f"{obj.creator.first_name} {obj.creator.last_name}".strip()
        return full_name or obj.creator.email or obj.creator.username

    def get_current_required_role(self, obj):
        return obj.current_required_role

    def validate_department(self, value):
        request = self.context.get("request")
        if value and request and request.user.company:
            if value.company_id != request.user.company_id:
                raise serializers.ValidationError(
                    "Ce département n'appartient pas à votre entreprise."
                )
        return value

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        request_obj = Request.objects.create(company=user.company, creator=user, **validated_data)
        start_request_sla(request_obj)
        return request_obj


class ApprovalSerializer(serializers.ModelSerializer):
    request_sla = serializers.SerializerMethodField()

    def get_request_sla(self, obj):
        return get_request_sla(obj.request)

    approver_name = serializers.SerializerMethodField()
    decision_display = serializers.CharField(source="get_decision_display", read_only=True)
    request_title = serializers.CharField(source="request.title", read_only=True)
    request_description = serializers.CharField(source="request.description", read_only=True)
    request_type_name = serializers.CharField(source="request.request_type.name", read_only=True)
    request_priority = serializers.CharField(source="request.priority", read_only=True)
    request_priority_display = serializers.CharField(
        source="request.get_priority_display", read_only=True
    )
    request_creator_name = serializers.SerializerMethodField()
    request_created_at = serializers.DateTimeField(source="request.created_at", read_only=True)

    class Meta:
        model = Approval
        fields = [
            "id",
            "request",
            "request_title",
            "request_description",
            "request_type_name",
            "request_priority",
            "request_priority_display",
            "request_creator_name",
            "request_created_at",
            "step",
            "required_role",
            "approver",
            "approver_name",
            "decision",
            "decision_display",
            "comment",
            "created_at",
            "decided_at",
            "request_sla",
        ]
        read_only_fields = [
            "id",
            "request_title",
            "request_description",
            "request_type_name",
            "request_priority",
            "request_priority_display",
            "request_creator_name",
            "request_created_at",
            "step",
            "required_role",
            "approver",
            "approver_name",
            "decision",
            "decision_display",
            "created_at",
            "decided_at",
            "request_sla",
        ]

    def get_approver_name(self, obj):
        if not obj.approver:
            return None
        full_name = f"{obj.approver.first_name} {obj.approver.last_name}".strip()
        return full_name or obj.approver.email or obj.approver.username

    def get_request_creator_name(self, obj):
        creator = obj.request.creator
        if not creator:
            return None
        full_name = f"{creator.first_name} {creator.last_name}".strip()
        return full_name or creator.email or creator.username
