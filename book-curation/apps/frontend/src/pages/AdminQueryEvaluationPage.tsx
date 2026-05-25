import AdminLayout from "../components/admin/AdminLayout";
import AdminQueryEvaluationPanel from "../components/admin/AdminQueryEvaluationPanel";

const AdminQueryEvaluationPage = () => {
  return (
    <AdminLayout
      title="평가 관리"
      description="추천 모델 설정과 분리해 query payload, retrieval variant, rule weight 평가 job과 정성평가 결과를 관리합니다."
    >
      {/* 수정 포인트: 이 라우트는 ADMIN 전용 ProtectedRoute 뒤에서만 렌더링되므로 평가 실행 권한은 true로 전달합니다. */}
      <AdminQueryEvaluationPanel isAdmin />
    </AdminLayout>
  );
};

export default AdminQueryEvaluationPage;
