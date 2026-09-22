from rest_framework import serializers
from .models import MembershipPlan, UserMembership, EligibilityCheck


class MembershipPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MembershipPlan
        fields = '__all__'


class UserMembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model  = UserMembership
        fields = ['id', 'plan', 'country_code', 'started_at', 'expires_at', 'is_active']
        read_only_fields = ['id', 'started_at', 'is_active']


class UpgradeMembershipSerializer(serializers.Serializer):
    plan              = serializers.ChoiceField(choices=['silver', 'gold'])
    payment_reference = serializers.CharField()


class EligibilityCheckSerializer(serializers.ModelSerializer):
    documents = serializers.SerializerMethodField()

    class Meta:
        model = EligibilityCheck
        fields = [
            'id', 'pathway', 'status', 'visa_expiry', 'passport_expiry',
            'migration_doc_type', 'phone', 'email', 'destination_country',
            'destination_city', 'metadata', 'created_at', 'updated_at', 'documents',
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at', 'documents']

    def get_documents(self, obj):
        return [
            {'id': doc.id, 'document_type': doc.document_type, 'file': doc.file.url, 'uploaded_at': doc.uploaded_at}
            for doc in obj.documents.all()
        ]


class AdminEligibilityListSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    documents_count = serializers.IntegerField(source='documents.count', read_only=True)

    class Meta:
        model = EligibilityCheck
        fields = [
            'id', 'pathway', 'status', 'user_email', 'user_name',
            'phone', 'email', 'destination_country', 'destination_city',
            'documents_count', 'rejection_reason', 'created_at', 'reviewed_at',
        ]

    def get_user_name(self, obj):
        name = (obj.user.get_full_name() or '').strip()
        return name or obj.user.username


class AdminEligibilityDetailSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = EligibilityCheck
        fields = [
            'id', 'pathway', 'status', 'user_email', 'user_name',
            'visa_expiry', 'passport_expiry', 'migration_doc_type',
            'phone', 'email', 'destination_country', 'destination_city',
            'metadata', 'rejection_reason', 'created_at', 'updated_at', 'reviewed_at',
            'documents',
        ]

    def get_user_name(self, obj):
        name = (obj.user.get_full_name() or '').strip()
        return name or obj.user.username

    def get_documents(self, obj):
        return [
            {
                'id': doc.id,
                'document_type': doc.document_type,
                'document_type_display': doc.get_document_type_display(),
                'file': doc.file.url,
                'uploaded_at': doc.uploaded_at,
            }
            for doc in obj.documents.all()
        ]  
